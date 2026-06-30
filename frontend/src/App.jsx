import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import * as Dialog from '@radix-ui/react-dialog';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './styles.vietnam-history.css';
import './detail-history.css';

const API = window.location.origin;
const DEFAULT_START = { lat: 21.0285, lng: 105.8542, label: 'Hà Nội' };
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
  const [sites, setSites] = useState([]);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [selectedProvinces, setSelectedProvinces] = useState(() => new Set());
  const [selectedCategories, setSelectedCategories] = useState(() => new Set());
  const [activeSite, setActiveSite] = useState(null);
  const [detailSite, setDetailSite] = useState(null);
  const [popupPos, setPopupPos] = useState(null);
  const [query, setQuery] = useState('');
  const [plannerOpen, setPlannerOpen] = useState(false);
  const [step, setStep] = useState(1);
  const [planner, setPlanner] = useState({days:3,people:2,mode:'driving',tripDate:new Date().toISOString().slice(0,10),windowStart:'08:00',windowEnd:'18:00',startText:'',endText:'',maxDistanceKm:'',maxDurationMin:'',avoidHighways:false,avoidTolls:false});
  const [startPoint, setStartPoint] = useState(DEFAULT_START);
  const [endPoint, setEndPoint] = useState(null);
  const [route, setRoute] = useState(null);
  const [status, setStatus] = useState({type:'info',text:'Mở ấn triện “Tạo lịch trình” để bắt đầu hành trình qua các di sản Việt Nam.'});
  const [loading, setLoading] = useState(false);

  const provinces = useMemo(() => [...new Set(sites.map(s => s.province).filter(Boolean))].sort(), [sites]);
  const categories = useMemo(() => [...new Set(sites.flatMap(site => site.categories?.length ? site.categories : ['default']))].sort((a,b) => (CAT_LABELS[a] || a).localeCompare(CAT_LABELS[b] || b, 'vi')), [sites]);
  const searchSuggestions = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) return [];
    const siteMatches = sites.filter(site => site.name.toLowerCase().includes(text) || site.province.toLowerCase().includes(text)).slice(0, 6).map(site => ({type:'site', id:site.id, label:site.name, sub:site.province, site}));
    const provinceMatches = provinces.filter(province => province.toLowerCase().includes(text)).slice(0, 3).map(province => ({type:'province', id:province, label:province, sub:'Tỉnh/thành phố'}));
    return [...siteMatches, ...provinceMatches].slice(0, 8);
  }, [provinces, query, sites]);
  const filteredSites = useMemo(() => {
    const text = query.trim().toLowerCase();
    return sites.filter(site => {
      const siteCategories = site.categories?.length ? site.categories : ['default'];
      return (selectedProvinces.size === 0 || selectedProvinces.has(site.province)) &&
        (selectedCategories.size === 0 || siteCategories.some(cat => selectedCategories.has(cat))) &&
        (!text || site.name.toLowerCase().includes(text) || site.province.toLowerCase().includes(text) || siteCategories.some(cat => (CAT_LABELS[cat] || cat).toLowerCase().includes(text)));
    });
  }, [query, selectedCategories, selectedProvinces, sites]);
  const selectedSites = useMemo(() => [...selectedIds].map(id => sites.find(site => site.id === id)).filter(Boolean), [selectedIds, sites]);

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
    const bounds = new maplibregl.LngLatBounds();
    filteredSites.slice(0, 550).forEach(site => {
      if (!Number.isFinite(site.lat) || !Number.isFinite(site.lng)) return;
      const marker = new maplibregl.Marker({element:markerElement(site, selectedIds.has(site.id))}).setLngLat([site.lng, site.lat]).addTo(map);
      marker.getElement().addEventListener('click', () => focusSite(site));
      markersRef.current.push(marker);
      bounds.extend([site.lng, site.lat]);
    });
    if (!bounds.isEmpty() && !skipFitRef.current) map.fitBounds(bounds,{padding:80,maxZoom:12});
    skipFitRef.current = false;
  }, [filteredSites, selectedIds]);

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
    setPopupPos(null);
    setSelectedProvinces(new Set());
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
  async function updatePoint(kind) {
    const text = kind === 'start' ? planner.startText : planner.endText;
    const point = await geocode(text);
    if (!point) { setStatus({type:'error',text:`Không tìm thấy ${kind === 'start' ? 'điểm xuất phát' : 'điểm kết thúc'}.`}); return; }
    kind === 'start' ? setStartPoint(point) : setEndPoint(point);
    setStatus({type:'info',text:`${kind === 'start' ? 'Xuất phát' : 'Kết thúc'}: ${point.label}`});
  }
  function autoPickSites() { const max = Math.max(1, Number(planner.days) || 1) * 5; return sites.filter(s => selectedProvinces.size === 0 || selectedProvinces.has(s.province)).sort((a,b) => (b.popularity_score||.5)+(b.historical_importance_score||.5)-((a.popularity_score||.5)+(a.historical_importance_score||.5))).slice(0,max); }
  async function planRoute() {
    if (!selectedProvinces.size) { setStatus({type:'error',text:'Chọn ít nhất một tỉnh trước khi tạo lịch trình.'}); setStep(1); return; }
    if (planner.mode === 'transit') { setStatus({type:'error',text:'Phương tiện công cộng cần GTFS/OpenTripPlanner. Hiện hỗ trợ ô tô, xe máy, đi bộ qua OSRM.'}); setStep(3); return; }
    setLoading(true); setRoute(null);
    const chosen = selectedSites.length ? selectedSites : autoPickSites();
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
      const coords = day.polyline ? decodePolyline(day.polyline) : [];
      if (coords.length > 1) { const id = `route-${index}`; map.addSource(id,{type:'geojson',data:{type:'Feature',geometry:{type:'LineString',coordinates:coords}}}); map.addLayer({id,type:'line',source:id,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['#e94560','#f0a500','#4ecdc4'][index%3],'line-width':5,'line-opacity':.86}}); routeLayerIdsRef.current.push(id); coords.forEach(c => bounds.extend(c)); }
      day.stops?.forEach(stop => { const site = sites.find(item => item.id === stop.site_id); if (!site) return; const marker = new maplibregl.Marker({element:markerElement(site,true)}).setLngLat([site.lng,site.lat]).addTo(map); marker.getElement().addEventListener('click', () => setActiveSite(site)); routeMarkersRef.current.push(marker); bounds.extend([site.lng,site.lat]); });
    });
    if (!bounds.isEmpty()) map.fitBounds(bounds,{padding:100,maxZoom:13});
  }
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !activeSite) { setPopupPos(null); return; }
    const update = () => {
      const point = map.project([activeSite.lng, activeSite.lat]);
      setPopupPos({x:point.x, y:point.y});
    };
    update();
    map.on('move', update);
    map.on('zoom', update);
    return () => { map.off('move', update); map.off('zoom', update); };
  }, [activeSite]);

  return <div className="map-first-shell">
    <main className="map-wrap"><div ref={mapNodeRef} className="map" /></main>
    <SearchBox query={query} setQuery={setQuery} suggestions={searchSuggestions} choose={chooseSuggestion} />
    <div className="top-left-stack">
      <button className="create-trip-btn" onClick={() => setPlannerOpen(true)}><span>印</span>Tạo lịch trình</button>
      <StatusBanner status={status} />
    </div>
    <CategoryFilters categories={categories} selected={selectedCategories} toggle={toggleCategory} clear={() => setSelectedCategories(new Set())} />
    <PlannerDialog open={plannerOpen} setOpen={setPlannerOpen} step={step} setStep={setStep} sites={sites} provinces={provinces} selectedProvinces={selectedProvinces} toggleProvince={toggleProvince} selectedSites={selectedSites} toggleSelected={toggleSelected} setActiveSite={setActiveSite} planner={planner} setPlanner={setPlanner} updatePoint={updatePoint} useCenter={() => useProvinceCenter(selectedProvinces,setStartPoint,setEndPoint,setPlanner)} makeRoundTrip={() => { setEndPoint(startPoint); setPlanner(v => ({...v,endText:v.startText || `${startPoint.lat}, ${startPoint.lng}`})); }} loading={loading} planRoute={planRoute} />
    {route && <RouteSummary route={route} openPlanner={() => setPlannerOpen(true)} focus={id => { const site = sites.find(item => item.id === id); if (site) focusSite(site); }} />}
    {activeSite && popupPos && <MiniSitePopup site={activeSite} pos={popupPos} selected={selectedIds.has(activeSite.id)} toggle={() => toggleSelected(activeSite.id)} detail={() => setDetailSite(activeSite)} close={closeSitePopup} />}
    <SiteDetailDialog site={detailSite} selected={detailSite ? selectedIds.has(detailSite.id) : false} toggle={() => detailSite && toggleSelected(detailSite.id)} close={() => setDetailSite(null)} />
  </div>;
}

function PlannerDialog(props) {
  const {open,setOpen,step,setStep,provinces,selectedProvinces,toggleProvince,selectedSites,toggleSelected,setActiveSite,planner,setPlanner,updatePoint,useCenter,makeRoundTrip,loading,planRoute} = props;
  return <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="planner-modal"><div className="modal-hero"><Dialog.Title>Chiếu chỉ hành trình di sản</Dialog.Title><Dialog.Description>Chọn vùng đất, điểm ghé thăm và để hệ thống sắp xếp cung đường tối ưu.</Dialog.Description><Dialog.Close className="modal-close">×</Dialog.Close></div><div className="wizard-tabs">{['Vùng đất','Khởi hành','Lộ trình'].map((label,i) => <button key={label} className={step === i+1 ? 'active' : ''} onClick={() => setStep(i+1)}><span>{i+1}</span>{label}</button>)}</div><div className="wizard-body">{step === 1 && <section><h3>Chọn vùng đất và di sản</h3><p>Chọn tỉnh để lọc bản đồ. Bấm marker để xem thông tin, sau đó chọn các điểm bắt buộc trong hành trình.</p><div className="province-grid modal-grid">{provinces.slice(0,60).map(province => <button key={province} className={selectedProvinces.has(province) ? 'active' : ''} onClick={() => toggleProvince(province)}>{province}</button>)}</div><SelectedSites sites={selectedSites} remove={toggleSelected} focus={setActiveSite} /></section>}{step === 2 && <section><h3>Điểm khởi hành và hồi trình</h3><div className="grid-2"><label>Khởi hành<input value={planner.startText} onChange={e => setPlanner({...planner,startText:e.target.value})} onBlur={() => planner.startText && updatePoint('start')} placeholder="21.0285,105.8542 hoặc địa chỉ" /></label><label>Hồi trình<input value={planner.endText} onChange={e => setPlanner({...planner,endText:e.target.value})} onBlur={() => planner.endText && updatePoint('end')} placeholder="Mặc định quay về điểm đầu" /></label></div><div className="button-row"><button onClick={useCenter}>Lấy trung tâm tỉnh</button><button onClick={makeRoundTrip}>Đi về cùng điểm</button></div></section>}{step === 3 && <section><h3>Tùy chỉnh lộ trình</h3><div className="grid-2"><label>Số ngày<input type="number" min="1" max="14" value={planner.days} onChange={e => setPlanner({...planner,days:e.target.value})} /></label><label>Phương tiện<select value={planner.mode} onChange={e => setPlanner({...planner,mode:e.target.value})}><option value="driving">Ô tô</option><option value="motorbike">Xe máy</option><option value="walking">Đi bộ</option><option value="transit">Công cộng</option></select></label></div><div className="grid-2"><label>Ngày đi<input type="date" value={planner.tripDate} onChange={e => setPlanner({...planner,tripDate:e.target.value})} /></label><label>Số người<input type="number" min="1" value={planner.people} onChange={e => setPlanner({...planner,people:e.target.value})} /></label></div><div className="grid-2"><label>Giờ mở hành trình<input type="time" value={planner.windowStart} onChange={e => setPlanner({...planner,windowStart:e.target.value})} /></label><label>Giờ kết hành trình<input type="time" value={planner.windowEnd} onChange={e => setPlanner({...planner,windowEnd:e.target.value})} /></label></div><details><summary>Giới hạn nâng cao</summary><div className="grid-2"><label>Tối đa km<input type="number" min="0" value={planner.maxDistanceKm} onChange={e => setPlanner({...planner,maxDistanceKm:e.target.value})} placeholder="Không giới hạn" /></label><label>Tối đa phút<input type="number" min="0" value={planner.maxDurationMin} onChange={e => setPlanner({...planner,maxDurationMin:e.target.value})} placeholder="Không giới hạn" /></label></div><div className="checks"><label><input type="checkbox" checked={planner.avoidHighways} onChange={e => setPlanner({...planner,avoidHighways:e.target.checked})} /> Tránh cao tốc</label><label><input type="checkbox" checked={planner.avoidTolls} onChange={e => setPlanner({...planner,avoidTolls:e.target.checked})} /> Tránh trạm thu phí</label></div></details></section>}</div><div className="modal-footer"><button className="ghost" disabled={step === 1} onClick={() => setStep(step - 1)}>Quay lại</button>{step < 3 ? <button className="primary compact" onClick={() => setStep(step + 1)}>Tiếp tục</button> : <button className="primary compact" disabled={loading} onClick={planRoute}>{loading ? 'Đang khai mở lộ trình...' : 'Ban hành lịch trình'}</button>}</div></Dialog.Content></Dialog.Portal></Dialog.Root>;
}

function StatusBanner({status}) { return <div className={`status ${status.type}`}>{status.text}</div>; }
function SearchBox({query, setQuery, suggestions, choose}) { return <div className="map-search-center"><div className="map-search-card"><span>⌕</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Tìm kiếm trên bản đồ" />{query && <button onClick={() => setQuery('')}>×</button>}</div>{suggestions.length > 0 && <div className="search-suggestions">{suggestions.map(item => <button key={`${item.type}-${item.id}`} onClick={() => choose(item)}><span>{item.type === 'site' ? '⌖' : '◉'}</span><div><strong>{item.label}</strong><small>{item.sub}</small></div></button>)}</div>}</div>; }
function CategoryFilters({categories, selected, toggle, clear}) { return <aside className="category-filter"><div><strong>Loại địa điểm</strong>{selected.size > 0 && <button onClick={clear}>Tất cả</button>}</div>{categories.map(category => { const [color, icon] = CAT_STYLE[category] || CAT_STYLE.default; return <button key={category} className={selected.has(category) ? 'active' : ''} style={{'--cat-color': color}} onClick={() => toggle(category)}><span>{icon}</span>{CAT_LABELS[category] || category}</button>; })}</aside>; }
function SelectedSites({sites, remove, focus}) { return <div className="selected-box">{sites.length ? sites.map(site => <button key={site.id} onClick={() => focus(site)}>{site.name}<span onClick={e => {e.stopPropagation(); remove(site.id);}}>×</span></button>) : <p>Chưa ghim điểm nào. Hệ thống sẽ tự chọn điểm nổi bật trong tỉnh.</p>}</div>; }
function RouteSummary({route, openPlanner, focus}) { return <aside className="route-summary"><div className="summary"><strong>{route.status === 'feasible' ? 'Lộ trình khả thi' : 'Cần chỉnh lộ trình'}</strong><span>{route.total_distance_km} km</span><span>{route.total_duration_min} phút</span></div>{route.warnings?.map(w => <p className="warning" key={w}>{w}</p>)}<div className="route-days">{route.days?.map(day => <div className="day" key={day.day}><h3>Ngày {day.day}</h3>{day.stops?.map(stop => <button key={`${day.day}-${stop.site_id}`} onClick={() => focus(stop.site_id)}><time>{stop.arrival_time}</time><span>{stop.name}</span><small>{stop.travel_from_prev_km}km · {stop.travel_from_prev_min}p</small></button>)}</div>)}</div><button className="ghost full" onClick={openPlanner}>Chỉnh chiếu chỉ</button></aside>; }
function MiniSitePopup({site, pos, selected, toggle, detail, close}) { const cats = site.categories || []; return <div className="mini-site-popup" style={{left:pos.x, top:pos.y}}><button className="mini-close" onClick={close}>×</button><div className="site-kicker">Điểm di sản</div><h2>{site.name}</h2><p className="province">📍 {site.province}</p><div className="badges">{cats.slice(0,3).map(cat => <span key={cat}>{cat}</span>)}</div><p>{site.description || site.long_description || 'Đang cập nhật thông tin.'}</p><dl><dt>Giờ mở cửa</dt><dd>{site.opening_hours || '08:00-17:00'}</dd><dt>Thời lượng</dt><dd>{site.estimated_visit_minutes || 60} phút</dd><dt>Giá vé</dt><dd>{formatPrice(site.ticket_price)}</dd></dl><div className="site-actions"><button className="primary" onClick={toggle}>{selected ? 'Bỏ chọn' : 'Chọn điểm này'}</button><button className="ghost" onClick={detail}>Xem chi tiết</button></div></div>; }
function SiteDetailDialog({site, selected, toggle, close}) {
  const [images, setImages] = useState([]); const [reviews, setReviews] = useState([]); const [enriched, setEnriched] = useState(null); const [slide, setSlide] = useState(0); const open = Boolean(site);
  useEffect(() => { if (!site) return; let alive = true; setImages([]); setReviews([]); setEnriched(null); setSlide(0); Promise.allSettled([fetch(`${API}/api/v1/heritage-sites/${site.id}/images`).then(r => r.json()), fetch(`${API}/api/v1/heritage-sites/${site.id}/reviews`).then(r => r.json()), fetch(`${API}/api/v1/heritage-sites/${site.id}/enrich`).then(r => r.json())]).then(([img, rev, enr]) => { if (!alive) return; if (img.status === 'fulfilled') setImages(img.value.images || []); if (rev.status === 'fulfilled' && Array.isArray(rev.value)) setReviews(rev.value); if (enr.status === 'fulfilled') setEnriched(enr.value); }); return () => { alive = false; }; }, [site]);
  if (!site) return null;
  const current = images[slide]; const description = enriched?.long_description || site.long_description || site.description || 'Đang cập nhật thông tin.'; const tips = enriched?.visit_tips || site.visit_tips;
  return <Dialog.Root open={open} onOpenChange={value => !value && close()}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="detail-modal"><Dialog.Close className="modal-close">×</Dialog.Close><div className="detail-hero"><div className="detail-carousel">{current ? <img src={current.thumb_url || current.url} alt={current.title || site.name} /> : <div className="detail-placeholder"><span>{(CAT_STYLE[(site.categories || [])[0]] || CAT_STYLE.default)[1]}</span><strong>{site.name}</strong><small>Chưa có ảnh trong bộ sưu tập</small></div>}{images.length > 1 && <><button className="carousel-nav prev" onClick={() => setSlide((slide - 1 + images.length) % images.length)}>‹</button><button className="carousel-nav next" onClick={() => setSlide((slide + 1) % images.length)}>›</button><div className="carousel-dots">{images.map((_, i) => <button key={i} className={i === slide ? 'active' : ''} onClick={() => setSlide(i)} />)}</div></>}</div><div className="detail-heading"><div className="site-kicker">Hồ sơ di sản</div><Dialog.Title>{site.name}</Dialog.Title><Dialog.Description>📍 {site.province}</Dialog.Description><div className="badges">{(site.categories || []).map(cat => <span key={cat}>{cat}</span>)}</div><div className="site-actions"><button className="primary" onClick={toggle}>{selected ? 'Bỏ chọn khỏi hành trình' : 'Chọn vào hành trình'}</button><a className="ghost link-btn" href={`https://www.google.com/maps?q=${site.lat},${site.lng}`} target="_blank" rel="noreferrer">Mở bản đồ</a></div></div></div><div className="detail-body"><section><h3>Giới thiệu</h3><p>{description}</p>{tips && <div className="tips"><strong>Lưu ý tham quan</strong><p>{tips}</p></div>}</section><aside><dl><dt>Giờ mở cửa</dt><dd>{site.opening_hours || '08:00-17:00'}</dd><dt>Thời lượng</dt><dd>{site.estimated_visit_minutes || 60} phút</dd><dt>Giá vé</dt><dd>{formatPrice(site.ticket_price)}</dd><dt>Độ phổ biến</dt><dd>{scorePercent(site.popularity_score)}</dd><dt>Giá trị lịch sử</dt><dd>{scorePercent(site.historical_importance_score)}</dd></dl></aside><section className="reviews"><h3>Đánh giá nổi bật</h3>{reviews.length ? reviews.slice(0,4).map((review, i) => <article key={`${review.author}-${i}`}><div><strong>{review.author || 'Khách tham quan'}</strong><span>{stars(review.rating)}</span></div><p>{review.text}</p><small>{review.source || 'local'}</small></article>) : <p>Chưa có đánh giá. Hệ thống sẽ bổ sung khi có dữ liệu.</p>}</section></div></Dialog.Content></Dialog.Portal></Dialog.Root>;
}

function formatPrice(value) { return value ? `${Number(value).toLocaleString('vi-VN')}₫` : 'Miễn phí'; }
function scorePercent(value) { return `${Math.round((value || .5) * 100)}%`; }
function stars(value) { const rating = Math.max(0, Math.min(5, Math.round(value || 4))); return `${'★'.repeat(rating)}${'☆'.repeat(5 - rating)}`; }
function markerElement(site, selected) { const [color, icon] = CAT_STYLE[(site.categories || [])[0]] || CAT_STYLE.default; const el = document.createElement('button'); el.className = `map-marker ${selected ? 'selected' : ''}`; el.style.setProperty('--marker-color', color); el.textContent = icon; el.title = site.name; return el; }
function parseOpeningHours(value) { const matches = String(value || '').match(/\d{1,2}:\d{2}/g) || []; return {open_time:matches[0] || '08:00', close_time:matches[1] || '17:00'}; }
function toPlannerSite(site) { const hours = parseOpeningHours(site.opening_hours); return {id:site.id,name:site.name,lat:site.lat,lng:site.lng,open_time:hours.open_time,close_time:hours.close_time,visit_duration_min:site.estimated_visit_minutes || 60}; }
function optionalNumber(value) { if (value === '') return null; const n = Number(value); return Number.isFinite(n) ? n : null; }
function formatApiError(data) { if (Array.isArray(data?.detail)) return data.detail.map(item => `${item.loc?.join('.')}: ${item.msg}`).join('; '); return data?.warnings?.join('; ') || data?.detail || 'Không thể tạo tuyến.'; }
function useProvinceCenter(selectedProvinces,setStartPoint,setEndPoint,setPlanner) { const province = [...selectedProvinces][0]; const coords = PROV_COORDS[province]; if (!coords) return; const point = {lat:coords[0],lng:coords[1],label:province}; setStartPoint(point); setEndPoint(point); setPlanner(value => ({...value,startText:`${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`,endText:`${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`})); }
function decodePolyline(str, precision = 5) { let index = 0, lat = 0, lng = 0; const coords = []; const factor = 10 ** precision; while (index < str.length) { let result = 0, shift = 0, byte; do { byte = str.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20); lat += result & 1 ? ~(result >> 1) : result >> 1; result = 0; shift = 0; do { byte = str.charCodeAt(index++) - 63; result |= (byte & 0x1f) << shift; shift += 5; } while (byte >= 0x20); lng += result & 1 ? ~(result >> 1) : result >> 1; coords.push([lng / factor, lat / factor]); } return coords; }

createRoot(document.getElementById('root')).render(<App />);
