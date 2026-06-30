import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import * as Dialog from '@radix-ui/react-dialog';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './styles.vietnam-history.css';
import './detail-history.css';
import RoutePlayback from './RoutePlayback';

const API = window.location.origin;
const DEFAULT_START = { lat: 21.0285, lng: 105.8542, label: 'Hà Nội' };
const FEATURED_PER_PROVINCE = 3;
const PROV_COORDS = {'Hà Nội':[21.0285,105.8542],'TP. Hồ Chí Minh':[10.8231,106.6297],'Thừa Thiên Huế':[16.4637,107.5909],'Đà Nẵng':[16.0544,108.2022],'Quảng Nam':[15.8801,108.338],'Quảng Ninh':[20.9101,107.1839],'Ninh Bình':[20.2506,105.9745],'Lào Cai':[22.3356,103.8436],'Hà Giang':[23.2785,105.359],'Cần Thơ':[10.0328,105.7705]};
const CAT_STYLE = {
  history:['#9f1d19','✦'],
  spiritual:['#d7a84f','卍'],
  museum:['#6f3f20','鼎'],
  architecture:['#8a4b2a','門'],
  craft_village:['#2f6f5e','✺'],
  unesco:['#c47a1f','★'],
  nature:['#3f7a4c','山'],
  entertainment:['#a33f2d','◆'],
  default:['#7a5b35','•']
};
const CAT_LABELS = {history:'Lịch sử',spiritual:'Tâm linh',museum:'Bảo tàng',architecture:'Kiến trúc',craft_village:'Làng nghề',unesco:'UNESCO',nature:'Thiên nhiên',entertainment:'Giải trí',default:'Khác'};

function App() {
  const mapRef = useRef(null);
  const mapNodeRef = useRef(null);
  const markersRef = useRef([]);
  const routeMarkersRef = useRef([]);
  const routeLayerIdsRef = useRef([]);
  const skipFitRef = useRef(false);
  const hoverClearTimerRef = useRef(null);
  const hoverIntentTimerRef = useRef(null);
  const popupRef = useRef(null);
  const popupHoverRef = useRef(false);
  const [sites, setSites] = useState([]);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [selectedProvinces, setSelectedProvinces] = useState(() => new Set());
  const [selectedCategories, setSelectedCategories] = useState(() => new Set());
  const [activeSite, setActiveSite] = useState(null);
  const [hoverSite, setHoverSite] = useState(null);
  const [detailSite, setDetailSite] = useState(null);
  const [popupPos, setPopupPos] = useState(null);
  const [query, setQuery] = useState('');
  const [plannerOpen, setPlannerOpen] = useState(false);
  const [pickingMapFor, setPickingMapFor] = useState(null);
  const [step, setStep] = useState(1);
  const [planner, setPlanner] = useState({days:3,people:2,mode:'driving',tripDate:new Date().toISOString().slice(0,10),windowStart:'08:00',windowEnd:'18:00',startText:'',endText:'',maxDistanceKm:'',maxDurationMin:'',avoidHighways:false,avoidTolls:false});
  const [startPoint, setStartPoint] = useState(DEFAULT_START);
  const [endPoint, setEndPoint] = useState(null);
  const [route, setRoute] = useState(null);
  const [status, setStatus] = useState({type:'info',text:'Mở ấn triện “Tạo lịch trình” để bắt đầu hành trình qua các di sản Việt Nam.'});
  const [loading, setLoading] = useState(false);

  const provinces = useMemo(() => [...new Set(sites.map(s => s.province).filter(Boolean))].sort(), [sites]);
  const categories = useMemo(() => [...new Set(sites.flatMap(site => site.categories?.length ? site.categories : ['default']))].sort((a,b) => (CAT_LABELS[a] || a).localeCompare(CAT_LABELS[b] || b, 'vi')), [sites]);
  const featuredSites = useMemo(() => {
    const byProvince = new Map();
    sites.forEach(site => {
      if (!site.province) return;
      const list = byProvince.get(site.province) || [];
      list.push(site);
      byProvince.set(site.province, list);
    });
    return [...byProvince.values()].flatMap(list => list
      .sort((a, b) => siteRank(b) - siteRank(a))
      .slice(0, FEATURED_PER_PROVINCE));
  }, [sites]);
  const searchSuggestions = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) return [];
    const siteMatches = sites.filter(site => site.name.toLowerCase().includes(text) || site.province.toLowerCase().includes(text)).slice(0, 6).map(site => ({type:'site', id:site.id, label:site.name, sub:site.province, site}));
    const provinceMatches = provinces.filter(province => province.toLowerCase().includes(text)).slice(0, 3).map(province => ({type:'province', id:province, label:province, sub:'Tỉnh/thành phố'}));
    return [...siteMatches, ...provinceMatches].slice(0, 8);
  }, [provinces, query, sites]);
  const filteredSites = useMemo(() => {
    const source = selectedProvinces.size ? sites : featuredSites;
    return source.filter(site => {
      const siteCategories = site.categories?.length ? site.categories : ['default'];
      return (selectedProvinces.size === 0 || selectedProvinces.has(site.province)) &&
        (selectedCategories.size === 0 || siteCategories.some(cat => selectedCategories.has(cat)));
    });
  }, [featuredSites, selectedCategories, selectedProvinces, sites]);
  const selectedSites = useMemo(() => [...selectedIds].map(id => sites.find(site => site.id === id)).filter(Boolean), [selectedIds, sites]);
  const popupSite = hoverSite || activeSite;

  useEffect(() => { fetch(`${API}/api/v1/heritage-sites`).then(r => r.json()).then(d => setSites(Array.isArray(d) ? d : [])).catch(e => setStatus({type:'error',text:`Không tải được dữ liệu: ${e.message}`})); }, []);
  useEffect(() => { skipFitRef.current = true; }, [query]);
  useEffect(() => {
    if (mapRef.current || !mapNodeRef.current) return;
    mapRef.current = new maplibregl.Map({container:mapNodeRef.current,style:{version:8,sources:{osm:{type:'raster',tiles:['https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'],tileSize:256,attribution:'© CARTO | © OSM'}},layers:[{id:'osm',type:'raster',source:'osm'}]},center:[105.8542,21.0285],zoom:6});
    mapRef.current.addControl(new maplibregl.NavigationControl(),'top-right');
  }, []);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach(marker => marker.remove());
    markersRef.current = [];
    if (route) return;
    const bounds = new maplibregl.LngLatBounds();
    filteredSites.forEach(site => {
      if (!Number.isFinite(site.lat) || !Number.isFinite(site.lng)) return;
      const marker = new maplibregl.Marker({element:markerElement(site, selectedIds.has(site.id))}).setLngLat([site.lng, site.lat]).addTo(map);
      bindMarker(marker, site, () => focusSite(site));
      markersRef.current.push(marker);
      bounds.extend([site.lng, site.lat]);
    });
    if (!bounds.isEmpty() && !skipFitRef.current) map.fitBounds(bounds,{padding:80,maxZoom:12});
    skipFitRef.current = false;
  }, [filteredSites, selectedIds, route]);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    
    if (pickingMapFor) {
      map.getCanvas().style.cursor = 'crosshair';
    } else {
      map.getCanvas().style.cursor = '';
    }
    
    function onMapClick(e) {
      const lat = e.lngLat.lat;
      const lng = e.lngLat.lng;
      
      if (pickingMapFor) {
        reverseGeocode(lat, lng).then(label => {
          const point = {lat, lng, label};
          if (pickingMapFor === 'start') {
            setStartPoint(point);
            setPlanner(p => ({...p, startText: label}));
          } else {
            setEndPoint(point);
            setPlanner(p => ({...p, endText: label}));
          }
          setPickingMapFor(null);
          setPlannerOpen(true);
        });
      } else {
        const url = new URL(window.location);
        url.searchParams.set('lat', lat.toFixed(5));
        url.searchParams.set('lng', lng.toFixed(5));
        window.history.replaceState({}, '', url);
      }
    }
    map.on('click', onMapClick);
    return () => { map.off('click', onMapClick); map.getCanvas().style.cursor = ''; };
  }, [pickingMapFor]);

  function toggleProvince(province) {
    setSelectedProvinces(current => {
      const next = new Set(current);
      if (next.has(province)) next.delete(province); else next.add(province);
      if (!current.size && PROV_COORDS[province]) {
        const [lat,lng] = PROV_COORDS[province];
        const point = {lat,lng,label:province};
        setStartPoint(point); setEndPoint(point);
        setPlanner(value => ({...value,startText:`${lat.toFixed(4)}, ${lng.toFixed(4)}`,endText:`${lat.toFixed(4)}, ${lng.toFixed(4)}`}));
      }
      return next;
    });
  }
  function toggleSelected(id) { setSelectedIds(current => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next; }); }
  function toggleCategory(category) { setSelectedCategories(current => { const next = new Set(current); next.has(category) ? next.delete(category) : next.add(category); return next; }); }
  function bindMarker(marker, site, click) {
    const element = marker.getElement();
    element.addEventListener('click', click);
    element.addEventListener('mouseenter', () => {
      clearTimeout(hoverClearTimerRef.current);
      clearTimeout(hoverIntentTimerRef.current);
      if (popupHoverRef.current) return;
      hoverIntentTimerRef.current = setTimeout(() => setHoverSite(site), 140);
    });
    element.addEventListener('mouseleave', () => {
      clearTimeout(hoverIntentTimerRef.current);
      clearTimeout(hoverClearTimerRef.current);
      hoverClearTimerRef.current = setTimeout(() => {
        if (!popupHoverRef.current) setHoverSite(current => current?.id === site.id ? null : current);
      }, 260);
    });
  }
  function focusSite(site) {
    skipFitRef.current = true;
    setSelectedProvinces(new Set([site.province]));
    setActiveSite(site);
    const map = mapRef.current;
    if (map && Number.isFinite(site.lng) && Number.isFinite(site.lat)) {
      const updatePopup = () => {
        const point = map.project([site.lng, site.lat]);
        setPopupPos({x:point.x, y:point.y});
      };
      setPopupPos(null);
      map.once('moveend', updatePopup);
      map.easeTo({center:[site.lng, site.lat], zoom:Math.max(map.getZoom(), 9.5), duration:650, essential:true});
    }
  }
  function closeSitePopup() {
    setActiveSite(null);
    setHoverSite(null);
    setPopupPos(null);
  }
  function resetMapFocus() {
    skipFitRef.current = true;
    setSelectedProvinces(new Set());
    setActiveSite(null);
    setHoverSite(null);
    setPopupPos(null);
    mapRef.current?.easeTo({center:[106.2,16.2], zoom:5.4, duration:650, essential:true});
  }
  function chooseSuggestion(item) {
    if (item.type === 'site') {
      setQuery(item.label);
      focusSite(item.site);
      return;
    }
    setQuery(item.label);
    setSelectedProvinces(new Set([item.label]));
    setActiveSite(null);
    setPopupPos(null);
    const coords = PROV_COORDS[item.label];
    if (coords && mapRef.current) mapRef.current.easeTo({center:[coords[1], coords[0]], zoom:8, duration:650, essential:true});
  }
  async function geocode(text) {
    const raw = text.trim();
    const pair = raw.match(/^(-?\d+\.?\d*)[,;]\s*(-?\d+\.?\d*)$/);
    if (pair) return {lat:Number(pair[1]), lng:Number(pair[2]), label:raw};
    if (!raw) return null;
    const response = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(`${raw} Vietnam`)}&format=json&limit=1&countrycodes=vn`);
    const data = await response.json();
    return data?.length ? {lat:Number(data[0].lat),lng:Number(data[0].lon),label:data[0].display_name} : null;
  }
  async function reverseGeocode(lat, lng) {
    try {
      const response = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&accept-language=vi`);
      const data = await response.json();
      return data?.display_name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    } catch {
      return `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    }
  }
  async function pickLocation(kind) {
    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(async (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        const label = await reverseGeocode(lat, lng);
        const point = {lat, lng, label};
        if (kind === 'start') {
          setStartPoint(point);
          setPlanner(p => ({...p, startText: label}));
        } else {
          setEndPoint(point);
          setPlanner(p => ({...p, endText: label}));
        }
      }, (error) => {
         setStatus({type:'error',text:'Không lấy được vị trí.'});
      });
    } else {
      setStatus({type:'error',text:'Trình duyệt không hỗ trợ geolocation.'});
    }
  }
  function startPickingMap(kind) {
    setPickingMapFor(kind);
    setPlannerOpen(false);
    setStatus({type: 'info', text: 'Vui lòng click vào một điểm trên bản đồ.'});
  }
  async function updatePoint(kind, textOverride=null) {
    const text = textOverride ?? (kind === 'start' ? planner.startText : planner.endText);
    const point = await geocode(text);
    if (!point) { setStatus({type:'error',text:`Không tìm thấy ${kind === 'start' ? 'điểm xuất phát' : 'điểm kết thúc'}.`}); return; }
    if (kind === 'start') {
       setStartPoint(point);
       setPlanner(p => ({...p, startText: point.label}));
    } else {
       setEndPoint(point);
       setPlanner(p => ({...p, endText: point.label}));
    }
    setStatus({type:'info',text:`${kind === 'start' ? 'Xuất phát' : 'Kết thúc'}: ${point.label}`});
  }
  async function recommendRoute() {
    const interestText = (planner.selectedInterests || []).join(', ');
    if (!interestText) {
      setStatus({type:'error',text:'Vui lòng chọn ít nhất 1 điểm di sản hoặc tick vào sở thích để hệ thống gợi ý.'});
      setStep(1); return;
    }
    setLoading(true); setRoute(null);
    const resolvedEnd = endPoint || startPoint;
    const body = {
      raw_text: interestText,
      destination_provinces: [...selectedProvinces],
      start_date: planner.tripDate,
      duration_days: Number(planner.days) || 1,
      number_of_people: Number(planner.people) || 2,
      travel_mode: planner.mode,
      start_lat: startPoint.lat,
      start_lng: startPoint.lng,
      end_lat: resolvedEnd.lat,
      end_lng: resolvedEnd.lng
    };
    try {
      const response = await fetch(`${API}/api/v1/trips/recommend`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data = await response.json();
      if (!response.ok) throw new Error(formatApiError(data));
      const mappedRoute = {
        status: 'feasible',
        total_distance_km: data.total_distance_km,
        total_duration_min: (data.days || []).reduce((acc, day) => {
           return acc + (day.items || []).reduce((a, item) => {
              let visit = 60;
              if (item.time && item.time.includes('-')) {
                  const parts = item.time.split('-');
                  const [h1, m1] = parts[0].split(':').map(Number);
                  const [h2, m2] = parts[1].split(':').map(Number);
                  if (!isNaN(h1) && !isNaN(h2)) {
                      visit = (h2 * 60 + (m2 || 0)) - (h1 * 60 + (m1 || 0));
                      if (visit < 0) visit += 24 * 60;
                  }
              }
              return a + (item.travel_from_previous_minutes || 0) + visit;
           }, 0);
        }, 0),
        summary: data.summary,
        warnings: [],
        days: (data.days || []).map((d, i) => ({
           day: d.day,
           coordinates: data.route_geometries?.[i] || [],
           stops: (d.items || []).map(item => ({
              site_id: item.ref_id,
              name: item.name,
              arrival_time: (item.time || '').split('-')[0] || '',
              travel_from_prev_km: (item.distance_from_previous_m || 0) / 1000,
              travel_from_prev_min: item.travel_from_previous_minutes || 0
           }))
        }))
      };
      setRoute(mappedRoute); drawRoute(mappedRoute); setPlannerOpen(false);
      setStatus({type:'success',text:'AI đã thiết kế lịch trình thành công.'});
    } catch (error) { setStatus({type:'error',text:error.message || 'Không thể tạo gợi ý.'}); }
    finally { setLoading(false); }
  }

  async function planRoute() {
    if (!selectedProvinces.size) { setStatus({type:'error',text:'Chọn ít nhất một tỉnh trước khi tạo lịch trình.'}); setStep(1); return; }
    if (planner.mode === 'transit') { setStatus({type:'error',text:'Phương tiện công cộng cần GTFS/OpenTripPlanner. Hiện hỗ trợ ô tô, xe máy, đi bộ qua OSRM.'}); setStep(3); return; }
    if (selectedSites.length === 0) return recommendRoute();
    setLoading(true); setRoute(null);
    const chosen = selectedSites;
    const resolvedEnd = endPoint || startPoint;
    const body = {province:[...selectedProvinces].join(', '),sites:chosen.map(toPlannerSite),start:{id:null,lat:startPoint.lat,lng:startPoint.lng,label:startPoint.label||'Start'},end:{id:null,lat:resolvedEnd.lat,lng:resolvedEnd.lng,label:resolvedEnd.label||'End'},transport_mode:planner.mode,trip_date:planner.tripDate,available_window:{start_time:planner.windowStart,end_time:planner.windowEnd},num_days:Number(planner.days)||1,constraints:{avoid_highways:planner.avoidHighways,avoid_tolls:planner.avoidTolls,max_total_distance_km:optionalNumber(planner.maxDistanceKm),max_total_duration_min:optionalNumber(planner.maxDurationMin)}};
    try {
      const response = await fetch(`${API}/api/v1/routes/plan`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data = await response.json();
      if (!response.ok || data.status === 'error') throw new Error(formatApiError(data));
      setRoute(data); drawRoute(data); setPlannerOpen(false);
      setStatus({type:data.status === 'feasible' ? 'success' : 'warning',text:data.status === 'feasible' ? 'Tuyến đã sẵn sàng.' : 'Tuyến vượt một số giới hạn, xem cảnh báo.'});
    } catch (error) { setStatus({type:'error',text:error.message || 'Không thể tạo tuyến.'}); }
    finally { setLoading(false); }
  }
  function drawRoute(data) {
    const map = mapRef.current; if (!map) return;
    routeLayerIdsRef.current.forEach(id => { if (map.getLayer(id)) map.removeLayer(id); if (map.getSource(id)) map.removeSource(id); }); routeLayerIdsRef.current = [];
    routeMarkersRef.current.forEach(marker => marker.remove()); routeMarkersRef.current = [];
    const bounds = new maplibregl.LngLatBounds();
    data.days?.forEach((day,index) => {
      const coords = day.coordinates?.length ? day.coordinates : (day.polyline ? decodePolyline(day.polyline) : []);
      if (coords.length > 1) { const id = `route-${index}`; map.addSource(id,{type:'geojson',data:{type:'Feature',geometry:{type:'LineString',coordinates:coords}}}); map.addLayer({id,type:'line',source:id,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['#e94560','#f0a500','#4ecdc4'][index%3],'line-width':5,'line-opacity':.86}}); routeLayerIdsRef.current.push(id); coords.forEach(c => bounds.extend(c)); }
      day.stops?.forEach(stop => { const site = sites.find(item => item.id === stop.site_id); if (!site) return; const marker = new maplibregl.Marker({element:markerElement(site,true)}).setLngLat([site.lng,site.lat]).addTo(map); bindMarker(marker, site, () => setActiveSite(site)); routeMarkersRef.current.push(marker); bounds.extend([site.lng,site.lat]); });
    });
    if (!bounds.isEmpty()) map.fitBounds(bounds,{padding:100,maxZoom:13});
  }
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !popupSite) { setPopupPos(null); return; }
    // Initialize standard pos so it renders once
    const initialPoint = map.project([popupSite.lng, popupSite.lat]);
    setPopupPos({x: initialPoint.x, y: initialPoint.y});
    
    const update = () => {
      if (!popupRef.current) return;
      const point = map.project([popupSite.lng, popupSite.lat]);
      popupRef.current.style.transform = `translate(${point.x}px, ${point.y}px)`;
      popupRef.current.style.left = '0';
      popupRef.current.style.top = '0';
    };
    
    map.on('move', update);
    map.on('zoom', update);
    // Request animation frame for smoother initialization if needed
    requestAnimationFrame(update);
    return () => { map.off('move', update); map.off('zoom', update); };
  }, [popupSite]);

  return <div className="map-first-shell">
    <main className="map-wrap"><div ref={mapNodeRef} className="map" /></main>
    <SearchBox query={query} setQuery={setQuery} suggestions={searchSuggestions} choose={chooseSuggestion} />
    <div className="top-left-stack">
      <button className="create-trip-btn" onClick={() => setPlannerOpen(true)}><span>印</span>Tạo lịch trình</button>
      <StatusBanner status={status} />
    </div>
    {selectedProvinces.size > 0 && <button className="reset-map-btn" onClick={resetMapFocus}>Tắt zoom</button>}
    <CategoryFilters categories={categories} selected={selectedCategories} toggle={toggleCategory} clear={() => setSelectedCategories(new Set())} />
    
    {!plannerOpen && !pickingMapFor && !route && (
      <button className="floating-return-btn" onClick={() => setPlannerOpen(true)}>
        Quay lại lịch trình
      </button>
    )}

    <PlannerDialog open={plannerOpen} setOpen={setPlannerOpen} step={step} setStep={setStep} sites={sites} provinces={provinces} selectedProvinces={selectedProvinces} toggleProvince={toggleProvince} selectedSites={selectedSites} toggleSelected={toggleSelected} setActiveSite={setActiveSite} planner={planner} setPlanner={setPlanner} updatePoint={updatePoint} useCenter={() => useProvinceCenter(selectedProvinces,setStartPoint,setEndPoint,setPlanner)} makeRoundTrip={() => { setEndPoint(startPoint); setPlanner(v => ({...v,endText:v.startText || `${startPoint.lat}, ${startPoint.lng}`})); }} loading={loading} planRoute={planRoute} pickLocation={pickLocation} startPickingMap={startPickingMap} hideModal={() => setPlannerOpen(false)} />
    {route && <RouteSummary route={route} openPlanner={() => setPlannerOpen(true)} focus={id => { const site = sites.find(item => item.id === id); if (site) focusSite(site); }} />}
    {route && <RoutePlayback route={route} map={mapRef.current} sites={sites} />}
    {popupSite && popupPos && <MiniSitePopup site={popupSite} pos={popupPos} popupRef={popupRef} selected={selectedIds.has(popupSite.id)} toggle={() => toggleSelected(popupSite.id)} detail={() => setDetailSite(popupSite)} close={closeSitePopup} keepHover={() => { popupHoverRef.current = true; clearTimeout(hoverClearTimerRef.current); clearTimeout(hoverIntentTimerRef.current); }} endHover={() => { popupHoverRef.current = false; setHoverSite(null); }} />}
    <SiteDetailDialog site={detailSite} selected={detailSite ? selectedIds.has(detailSite.id) : false} toggle={() => detailSite && toggleSelected(detailSite.id)} close={() => setDetailSite(null)} />
  </div>;
}

function PlannerDialog(props) {
  const {open,setOpen,step,setStep,provinces,selectedProvinces,toggleProvince,selectedSites,toggleSelected,setActiveSite,planner,setPlanner,updatePoint,useCenter,makeRoundTrip,loading,planRoute,pickLocation,startPickingMap} = props;
  return <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="planner-modal"><div className="modal-hero"><Dialog.Title>Chiếu chỉ hành trình di sản</Dialog.Title><Dialog.Description>Chọn vùng đất, điểm ghé thăm và để hệ thống sắp xếp cung đường tối ưu.</Dialog.Description><Dialog.Close className="modal-close">×</Dialog.Close></div><div className="wizard-tabs">{['Vùng đất','Khởi hành','Lộ trình'].map((label,i) => <button key={label} className={step === i+1 ? 'active' : ''} onClick={() => setStep(i+1)}><span>{i+1}</span>{label}</button>)}</div><div className="wizard-body">{step === 1 && <section><h3>Chọn vùng đất và di sản</h3><p>Chọn tỉnh để lọc bản đồ. Bấm marker để xem thông tin, sau đó chọn các điểm bắt buộc trong hành trình.</p><div className="province-grid modal-grid">{provinces.slice(0,60).map(province => <button key={province} className={selectedProvinces.has(province) ? 'active' : ''} onClick={() => toggleProvince(province)}>{province}</button>)}</div><SelectedSites sites={selectedSites} remove={toggleSelected} focus={setActiveSite} />{selectedSites.length === 0 && <div style={{marginTop: 15, padding: 15, background: '#f8fafc', borderRadius: 14, border: '1px dashed #cbd5e1'}}><label style={{marginTop: 0, marginBottom: 10, color: '#334155'}}>Hoặc để AI tự gợi ý địa điểm theo sở thích</label><div style={{display: 'flex', flexWrap: 'wrap', gap: 8}}>{['Đền chùa & Tâm linh', 'Lịch sử & Khảo cổ', 'Kiến trúc & Nghệ thuật', 'Cảnh quan thiên nhiên', 'Trải nghiệm văn hóa địa phương', 'Thích hợp cho trẻ em', 'Thích hợp người lớn tuổi'].map(interest => { const isSelected = (planner.selectedInterests || []).includes(interest); return <button key={interest} type="button" className={`ghost ${isSelected ? 'active' : ''}`} style={{borderRadius: 20, padding: '6px 12px', borderColor: isSelected ? '#14b8a6' : 'var(--line)', background: isSelected ? '#ccfbf1' : '#fff', color: isSelected ? '#0f766e' : '#475569'}} onClick={() => { const current = planner.selectedInterests || []; setPlanner({...planner, selectedInterests: isSelected ? current.filter(i => i !== interest) : [...current, interest]}); }}>{interest}</button>; })}</div></div>}<div style={{marginTop: 15, textAlign: 'center'}}><button type="button" className="ghost" onClick={() => setOpen(false)}>Thu nhỏ để chọn trên bản đồ 🗺️</button></div></section>}{step === 2 && <section><h3>Điểm khởi hành và hồi trình</h3><div className="grid-2"><label>Khởi hành<div style={{display:'flex',gap:'4px'}}><input style={{flex:1}} value={planner.startText} onChange={e => setPlanner({...planner,startText:e.target.value})} onBlur={() => planner.startText && updatePoint('start')} placeholder="21.0285,105.8542 hoặc địa chỉ" /><button type="button" className="ghost" style={{padding:'0 8px'}} title="Vị trí hiện tại" onClick={() => pickLocation('start')}>📍</button><button type="button" className="ghost" style={{padding:'0 8px'}} title="Chọn trên bản đồ" onClick={() => startPickingMap('start')}>🗺️</button></div></label><label>Hồi trình<div style={{display:'flex',gap:'4px'}}><input style={{flex:1}} value={planner.endText} onChange={e => setPlanner({...planner,endText:e.target.value})} onBlur={() => planner.endText && updatePoint('end')} placeholder="Mặc định quay về điểm đầu" /><button type="button" className="ghost" style={{padding:'0 8px'}} title="Vị trí hiện tại" onClick={() => pickLocation('end')}>📍</button><button type="button" className="ghost" style={{padding:'0 8px'}} title="Chọn trên bản đồ" onClick={() => startPickingMap('end')}>🗺️</button></div></label></div><div className="button-row"><button type="button" onClick={useCenter}>Lấy trung tâm tỉnh</button><button type="button" onClick={makeRoundTrip}>Đi về cùng điểm</button></div></section>}{step === 3 && <section><h3>Tùy chỉnh lộ trình</h3><div className="grid-2"><label>Số ngày<input type="number" min="1" max="14" value={planner.days} onChange={e => setPlanner({...planner,days:e.target.value})} /></label><label>Phương tiện<select value={planner.mode} onChange={e => setPlanner({...planner,mode:e.target.value})}><option value="driving">Ô tô</option><option value="motorbike">Xe máy</option><option value="walking">Đi bộ</option><option value="transit">Công cộng</option></select></label></div><div className="grid-2"><label>Ngày đi<input type="date" value={planner.tripDate} onChange={e => setPlanner({...planner,tripDate:e.target.value})} /></label><label>Số người<input type="number" min="1" value={planner.people} onChange={e => setPlanner({...planner,people:e.target.value})} /></label></div><div className="grid-2"><label>Giờ mở hành trình<input type="time" value={planner.windowStart} onChange={e => setPlanner({...planner,windowStart:e.target.value})} /></label><label>Giờ kết hành trình<input type="time" value={planner.windowEnd} onChange={e => setPlanner({...planner,windowEnd:e.target.value})} /></label></div><details><summary>Giới hạn nâng cao</summary><div className="grid-2"><label>Tối đa km<input type="number" min="0" value={planner.maxDistanceKm} onChange={e => setPlanner({...planner,maxDistanceKm:e.target.value})} placeholder="Không giới hạn" /></label><label>Tối đa phút<input type="number" min="0" value={planner.maxDurationMin} onChange={e => setPlanner({...planner,maxDurationMin:e.target.value})} placeholder="Không giới hạn" /></label></div><div className="checks"><label><input type="checkbox" checked={planner.avoidHighways} onChange={e => setPlanner({...planner,avoidHighways:e.target.checked})} /> Tránh cao tốc</label><label><input type="checkbox" checked={planner.avoidTolls} onChange={e => setPlanner({...planner,avoidTolls:e.target.checked})} /> Tránh trạm thu phí</label></div></details></section>}</div><div className="modal-footer"><button type="button" className="ghost" disabled={step === 1} onClick={() => setStep(step - 1)}>Quay lại</button>{step < 3 ? <button type="button" className="primary compact" onClick={() => setStep(step + 1)}>Tiếp tục</button> : <button type="button" className="primary compact" disabled={loading} onClick={planRoute}>{loading ? 'Đang khai mở lộ trình...' : 'Ban hành lịch trình'}</button>}</div></Dialog.Content></Dialog.Portal></Dialog.Root>;
}

function StatusBanner({status}) { return <div className={`status ${status.type}`}>{status.text}</div>; }
function SearchBox({query, setQuery, suggestions, choose}) { return <div className="map-search-center"><div className="map-search-card"><span>⌕</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Tìm kiếm trên bản đồ" />{query && <button onClick={() => setQuery('')}>×</button>}</div>{suggestions.length > 0 && <div className="search-suggestions">{suggestions.map(item => <button key={`${item.type}-${item.id}`} onClick={() => choose(item)}><span>{item.type === 'site' ? '⌖' : '◉'}</span><div><strong>{item.label}</strong><small>{item.sub}</small></div></button>)}</div>}</div>; }
function CategoryFilters({categories, selected, toggle, clear}) { return <aside className="category-filter"><div><strong>Loại địa điểm</strong>{selected.size > 0 && <button onClick={clear}>Tất cả</button>}</div>{categories.map(category => { const [color, icon] = CAT_STYLE[category] || CAT_STYLE.default; return <button key={category} className={selected.has(category) ? 'active' : ''} style={{'--cat-color': color}} onClick={() => toggle(category)}><span>{icon}</span>{CAT_LABELS[category] || category}</button>; })}</aside>; }
function SelectedSites({sites, remove, focus}) { return <div className="selected-box">{sites.length ? sites.map(site => <button key={site.id} onClick={() => focus(site)}>{site.name}<span onClick={e => {e.stopPropagation(); remove(site.id);}}>×</span></button>) : <p>Chưa chọn điểm bắt buộc nào.</p>}</div>; }
function RouteSummary({route, openPlanner, focus}) { 
  const formatTime = (min) => {
    const m = Math.round(min);
    if (m < 60) return `${m} phút`;
    const h = Math.floor(m / 60);
    const m2 = m % 60;
    return m2 > 0 ? `${h}h ${m2}p` : `${h}h`;
  };
  return <aside className="route-summary"><div className="summary"><strong>{route.status === 'feasible' ? 'Lộ trình khả thi' : 'Cần chỉnh lộ trình'}</strong><span>{Number(route.total_distance_km).toFixed(2)} km</span><span>{formatTime(route.total_duration_min)}</span></div>{route.summary && <p className="ai-summary" style={{fontSize:13, color:'#475569', lineHeight:1.5, marginTop:10, padding:12, background:'#f8fafc', borderRadius:12}}>{route.summary}</p>}{route.warnings?.map(w => <p className="warning" key={w}>{w}</p>)}<div className="route-days">{route.days?.map(day => <div className="day" key={day.day}><h3>Ngày {day.day}</h3>{day.stops?.map(stop => <button key={`${day.day}-${stop.site_id}`} onClick={() => focus(stop.site_id)}><time>{stop.arrival_time}</time><span>{stop.name}</span><small>{Number(stop.travel_from_prev_km).toFixed(2)}km · {formatTime(stop.travel_from_prev_min)}</small></button>)}</div>)}</div><button className="ghost full" onClick={openPlanner}>Chỉnh sửa lịch trình</button></aside>; 
}
function MiniSitePopup({site, pos, popupRef, selected, toggle, detail, close, keepHover, endHover}) { const cats = site.categories || []; return <div ref={popupRef} className="mini-site-popup" style={{left:pos.x, top:pos.y}} onMouseEnter={keepHover} onMouseLeave={endHover}><button className="mini-close" onClick={close}>×</button><div className="site-kicker">Điểm di sản</div><h2>{site.name}</h2><p className="province">📍 {site.province}</p><div className="badges">{cats.slice(0,3).map(cat => <span key={cat}>{cat}</span>)}</div><p>{site.description || site.long_description || 'Đang cập nhật thông tin.'}</p><dl><dt>Giờ mở cửa</dt><dd>{site.opening_hours || '08:00-17:00'}</dd><dt>Thời lượng</dt><dd>{site.estimated_visit_minutes || 60} phút</dd><dt>Giá vé</dt><dd>{formatPrice(site.ticket_price)}</dd></dl><div className="site-actions"><button className="primary" onClick={toggle}>{selected ? 'Bỏ chọn' : 'Chọn điểm này'}</button><button className="ghost" onClick={detail}>Xem chi tiết</button></div></div>; }
function SiteDetailDialog({site, selected, toggle, close}) {
  const [images, setImages] = useState([]); const [reviews, setReviews] = useState([]); const [enriched, setEnriched] = useState(null); const [slide, setSlide] = useState(0); const open = Boolean(site);
  useEffect(() => { if (!site) return; let alive = true; setImages([]); setReviews([]); setEnriched(null); setSlide(0); Promise.allSettled([fetch(`${API}/api/v1/heritage-sites/${site.id}/images`).then(r => r.json()), fetch(`${API}/api/v1/heritage-sites/${site.id}/reviews`).then(r => r.json()), fetch(`${API}/api/v1/heritage-sites/${site.id}/enrich`).then(r => r.json())]).then(([img, rev, enr]) => { if (!alive) return; if (img.status === 'fulfilled') setImages(img.value.images || []); if (rev.status === 'fulfilled' && Array.isArray(rev.value)) setReviews(rev.value); if (enr.status === 'fulfilled') setEnriched(enr.value); }); return () => { alive = false; }; }, [site]);
  if (!site) return null;
  const current = images[slide]; const description = enriched?.long_description || site.long_description || site.description || 'Đang cập nhật thông tin.'; const tips = enriched?.visit_tips || site.visit_tips;
  return <Dialog.Root open={open} onOpenChange={value => !value && close()}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="detail-modal"><Dialog.Close className="modal-close">×</Dialog.Close><div className="detail-hero"><div className="detail-carousel">{current ? <img src={current.thumb_url || current.url} alt={current.title || site.name} /> : <div className="detail-placeholder"><span>{(CAT_STYLE[(site.categories || [])[0]] || CAT_STYLE.default)[1]}</span><strong>{site.name}</strong><small>Chưa có ảnh trong bộ sưu tập</small></div>}{images.length > 1 && <><button className="carousel-nav prev" onClick={() => setSlide((slide - 1 + images.length) % images.length)}>‹</button><button className="carousel-nav next" onClick={() => setSlide((slide + 1) % images.length)}>›</button><div className="carousel-dots">{images.map((_, i) => <button key={i} className={i === slide ? 'active' : ''} onClick={() => setSlide(i)} />)}</div></>}</div><div className="detail-heading"><div className="site-kicker">Hồ sơ di sản</div><Dialog.Title>{site.name}</Dialog.Title><Dialog.Description>📍 {site.province}</Dialog.Description><div className="badges">{(site.categories || []).map(cat => <span key={cat}>{cat}</span>)}</div><div className="site-actions"><button className="primary" onClick={toggle}>{selected ? 'Bỏ chọn khỏi hành trình' : 'Chọn vào hành trình'}</button><a className="ghost link-btn" href={`https://www.google.com/maps?q=${site.lat},${site.lng}`} target="_blank" rel="noreferrer">Mở bản đồ</a></div></div></div><div className="detail-body"><section><h3>Giới thiệu</h3><p>{description}</p>{tips && <div className="tips"><strong>Lưu ý tham quan</strong><p>{tips}</p></div>}</section><aside><dl><dt>Giờ mở cửa</dt><dd>{site.opening_hours || '08:00-17:00'}</dd><dt>Thời lượng</dt><dd>{site.estimated_visit_minutes || 60} phút</dd><dt>Giá vé</dt><dd>{formatPrice(site.ticket_price)}</dd><dt>Độ phổ biến</dt><dd>{scorePercent(site.popularity_score)}</dd><dt>Giá trị lịch sử</dt><dd>{scorePercent(site.historical_importance_score)}</dd></dl></aside><section className="reviews"><h3>Đánh giá nổi bật</h3>{reviews.length ? reviews.slice(0,4).map((review, i) => <article key={`${review.author}-${i}`}><div><strong>{review.author || 'Khách tham quan'}</strong><span>{stars(review.rating)}</span></div><p>{review.text}</p><small>{review.source || 'local'}</small></article>) : <p>Chưa có đánh giá. Hệ thống sẽ bổ sung khi có dữ liệu.</p>}</section></div></Dialog.Content></Dialog.Portal></Dialog.Root>;
}

function formatPrice(value) { return value ? `${Number(value).toLocaleString('vi-VN')}₫` : 'Miễn phí'; }
function scorePercent(value) { return `${Math.round((value || .5) * 100)}%`; }
function siteRank(site) { return (site.popularity_score || .5) + (site.historical_importance_score || .5); }
function stars(value) { const rating = Math.max(0, Math.min(5, Math.round(value || 4))); return `${'★'.repeat(rating)}${'☆'.repeat(5 - rating)}`; }
function markerElement(site, selected) { const [color, icon] = CAT_STYLE[(site.categories || [])[0]] || CAT_STYLE.default; const el = document.createElement('button'); el.className = `map-marker ${selected ? 'selected' : ''}`; el.style.setProperty('--marker-color', color); el.textContent = icon; el.title = site.name; return el; }
function parseOpeningHours(value) { const matches = String(value || '').match(/\d{1,2}:\d{2}/g) || []; return {open_time:matches[0] || '08:00', close_time:matches[1] || '17:00'}; }
function toPlannerSite(site) { const hours = parseOpeningHours(site.opening_hours); return {id:site.id,name:site.name,lat:site.lat,lng:site.lng,open_time:hours.open_time,close_time:hours.close_time,visit_duration_min:site.estimated_visit_minutes || 60}; }
function optionalNumber(value) { if (value === '') return null; const n = Number(value); return Number.isFinite(n) ? n : null; }
function formatApiError(data) { if (Array.isArray(data?.detail)) return data.detail.map(item => `${item.loc?.join('.')}: ${item.msg}`).join('; '); return data?.warnings?.join('; ') || data?.detail || 'Không thể tạo tuyến.'; }
function useProvinceCenter(selectedProvinces,setStartPoint,setEndPoint,setPlanner) { const province = [...selectedProvinces][0]; const coords = PROV_COORDS[province]; if (!coords) return; const point = {lat:coords[0],lng:coords[1],label:province}; setStartPoint(point); setEndPoint(point); setPlanner(value => ({...value,startText:`${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`,endText:`${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`})); }
function decodePolyline(str, precision = 5) { let index = 0, lat = 0, lng = 0; const coords = []; const factor = 10 ** precision; while (index < str.length) { let result = 0, shift = 0, byte; do { byte = str.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20); lat += result & 1 ? ~(result >> 1) : result >> 1; result = 0; shift = 0; do { byte = str.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20); lng += result & 1 ? ~(result >> 1) : result >> 1; coords.push([lng / factor, lat / factor]); } return coords; }

createRoot(document.getElementById('root')).render(<App />);
