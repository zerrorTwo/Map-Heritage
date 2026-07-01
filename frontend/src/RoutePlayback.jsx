import React, { useState, useEffect, useRef, useMemo } from 'react';
import maplibregl from 'maplibre-gl';
import * as turf from '@turf/turf';

function decodePolyline(str, precision = 5) {
  let index = 0, lat = 0, lng = 0, coordinates = [];
  let shift = 0, result = 0, byte = null;
  let latitude_change, longitude_change, factor = Math.pow(10, precision);
  while (index < str.length) {
    byte = null; shift = 0; result = 0;
    do { byte = str.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20);
    latitude_change = ((result & 1) ? ~(result >> 1) : (result >> 1));
    shift = result = 0;
    do { byte = str.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20);
    longitude_change = ((result & 1) ? ~(result >> 1) : (result >> 1));
    lat += latitude_change; lng += longitude_change;
    coordinates.push([lng / factor, lat / factor]);
  }
  return coordinates;
}

export default function RoutePlayback({ route, map, sites }) {
  const [activeDay, setActiveDay] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [narrateSite, setNarrateSite] = useState(null);
  const [narrationText, setNarrationText] = useState("");
  const [loadingNarration, setLoadingNarration] = useState(false);
  const [visitedStops, setVisitedStops] = useState(new Set());
  
  const markerRef = useRef(null);
  const animRef = useRef(null);
  const lastTimeRef = useRef(null);
  const progressRef = useRef(0);
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  
  // Update refs for animation loop
  useEffect(() => { progressRef.current = progress; }, [progress]);
  useEffect(() => { playingRef.current = playing; }, [playing]);
  useEffect(() => { speedRef.current = speed; }, [speed]);

  const currentDayData = useMemo(() => {
    if (!route || !route.days || !route.days[activeDay]) return null;
    const day = route.days[activeDay];
    const coords = day.coordinates?.length ? day.coordinates : (day.polyline ? decodePolyline(day.polyline) : []);
    if (coords.length < 2) return null;
    
    const lineString = turf.lineString(coords);
    const totalLength = turf.length(lineString, { units: 'kilometers' });
    
    // Map stops to their approximate distance along the route
    const stopsMap = [];
    if (day.stops) {
      day.stops.forEach(stop => {
        const site = sites.find(s => s.id === stop.site_id);
        if (site) {
          const pt = turf.point([site.lng, site.lat]);
          const nearest = turf.nearestPointOnLine(lineString, pt, { units: 'kilometers' });
          stopsMap.push({
            site,
            distance: nearest.properties.location, // distance along line
            stopData: stop
          });
        }
      });
    }
    // Sort stops by distance
    stopsMap.sort((a, b) => a.distance - b.distance);
    
    return { lineString, totalLength, stopsMap };
  }, [route, activeDay, sites]);

  // Handle Playback Animation Loop
  useEffect(() => {
    if (!map || !currentDayData) return;
    
    if (!markerRef.current) {
      const el = document.createElement('div');
      el.className = 'vehicle-marker';
      el.innerHTML = '🚗';
      markerRef.current = new maplibregl.Marker({ element: el })
        .setLngLat(currentDayData.lineString.geometry.coordinates[0])
        .addTo(map);
    }

    const animate = (time) => {
      if (playingRef.current) {
        const delta = time - (lastTimeRef.current || time);
        // speed 1 = roughly 100km per hour? No, let's just make speed visually pleasing.
        // Let's say 1 unit of speed = 50km per real second.
        const kmPerSec = 20 * speedRef.current;
        const deltaKm = kmPerSec * (delta / 1000);
        let newProgress = progressRef.current + deltaKm;
        
        if (newProgress >= currentDayData.totalLength) {
          newProgress = currentDayData.totalLength;
          setPlaying(false);
          playingRef.current = false;
        }

        // Check if we hit a stop we haven't visited
        for (const stop of currentDayData.stopsMap) {
          if (newProgress >= stop.distance && !visitedStops.has(stop.site.id)) {
            // Arrived at stop!
            setPlaying(false);
            playingRef.current = false;
            setNarrateSite(stop.site);
            setVisitedStops(prev => {
              const next = new Set(prev);
              next.add(stop.site.id);
              return next;
            });
            // Snap progress to stop
            newProgress = stop.distance;
            break;
          }
        }

        setProgress(newProgress);
        
        // Update Marker
        const along = turf.along(currentDayData.lineString, newProgress, { units: 'kilometers' });
        markerRef.current.setLngLat(along.geometry.coordinates);
        
        // Keep map centered occasionally or smoothly pan
        map.panTo(along.geometry.coordinates, { animate: false });
      }
      lastTimeRef.current = time;
      animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(animRef.current);
    };
  }, [map, currentDayData, visitedStops]);

  // Clean up marker on unmount or route change
  useEffect(() => {
    return () => {
      if (markerRef.current) {
        markerRef.current.remove();
        markerRef.current = null;
      }
    };
  }, [route]);

  const handleFetchNarration = async () => {
    if (!narrateSite) return;
    setLoadingNarration(true);
    try {
      const res = await fetch(`/api/v1/heritage-sites/${narrateSite.id}/narrate`);
      if (!res.ok) throw new Error(`Narration request failed: ${res.status}`);
      const data = await res.json();
      const narration = data.narration || narrateSite.long_description || narrateSite.description || "Hiện chưa có tư liệu thuyết minh cho địa điểm này.";
      setNarrationText(narration);
      
      // Auto text-to-speech if available
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(narration);
        utterance.lang = 'vi-VN';
        window.speechSynthesis.speak(utterance);
      }
    } catch (e) {
      console.error(e);
      setNarrationText("Lỗi khi tải thông tin. Vui lòng thử lại sau.");
    } finally {
      setLoadingNarration(false);
    }
  };

  const closeNarration = () => {
    setNarrateSite(null);
    setNarrationText("");
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    setPlaying(true); // Auto resume
  };

  if (!route || !route.days || route.days.length === 0) return null;

  return (
    <>
      <div className="playback-controller">
        <div className="playback-header">
          <strong>Hành trình mô phỏng</strong>
          <select value={activeDay} onChange={e => { setActiveDay(Number(e.target.value)); setProgress(0); setVisitedStops(new Set()); setPlaying(false); }}>
            {route.days.map((d, i) => (
              <option key={i} value={i}>Ngày {d.day}</option>
            ))}
          </select>
        </div>
        <div className="playback-controls">
          <button className="primary" onClick={() => setPlaying(!playing)}>
            {playing ? '⏸ Tạm dừng' : '▶ Phát'}
          </button>
          <button className="ghost" onClick={() => { setProgress(0); setVisitedStops(new Set()); }}>
            ⏮ Làm lại
          </button>
          <select className="speed-select" value={speed} onChange={e => setSpeed(Number(e.target.value))}>
            <option value={1}>1x Tốc độ</option>
            <option value={2}>2x</option>
            <option value={5}>5x</option>
            <option value={10}>10x</option>
          </select>
        </div>
        <div className="playback-progress">
          <input 
            type="range" 
            min={0} 
            max={currentDayData ? currentDayData.totalLength : 100} 
            value={progress} 
            onChange={e => {
              setProgress(Number(e.target.value));
              if (currentDayData) {
                const along = turf.along(currentDayData.lineString, Number(e.target.value), { units: 'kilometers' });
                if (markerRef.current) markerRef.current.setLngLat(along.geometry.coordinates);
                map.panTo(along.geometry.coordinates);
              }
            }}
          />
        </div>
      </div>

      {narrateSite && (
        <div className="narration-overlay">
          <div className="narration-popup">
            <h3>Đã đến: {narrateSite.name}</h3>
            {!narrationText ? (
              <div className="narration-prompt">
                <p>Bạn có muốn nghe thông tin và lịch sử về địa điểm này không?</p>
                <div className="actions">
                  <button className="primary" onClick={handleFetchNarration} disabled={loadingNarration}>
                    {loadingNarration ? <><i className="loading-spinner" aria-hidden="true" /> Đang tải...</> : 'Có, Kể tôi nghe 🔊'}
                  </button>
                  <button className="ghost" onClick={closeNarration} disabled={loadingNarration}>Bỏ qua</button>
                </div>
              </div>
            ) : (
              <div className="narration-content">
                <p>{narrationText}</p>
                <button className="primary" onClick={closeNarration}>Tiếp tục hành trình 🚙</button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
