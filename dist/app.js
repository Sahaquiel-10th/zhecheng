'use strict';
const icons = {
  heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  layers:'<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  grid:'<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="3" width="6" height="6" rx="1"/><rect x="3" y="15" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/>',
  list:'<path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  arrow:'<path d="m9 5 7 7-7 7"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || ''}</svg>`;
document.querySelectorAll('[data-icon]').forEach(el => el.outerHTML = icon(el.dataset.icon));
const $ = id => document.getElementById(id);
const escapeHtml = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const products = window.PRODUCTS;
const categoryOrder = ['全部好物','杯盏茶饮','纸笔书香','生活小景','随身好物','非遗雅作','节令礼遇'];
const params = new URLSearchParams(location.search);
const state = {category:categoryOrder.includes(params.get('category')) ? params.get('category') : '全部好物',query:params.get('q') || '',sort:['price-up','price-down'].includes(params.get('sort')) ? params.get('sort') : 'original',savedOnly:params.get('saved')==='1',view:'grid'};
let saved;
try { const raw = JSON.parse(localStorage.getItem('zhecheng-favorites') || '[]'); saved = new Set(Array.isArray(raw) ? raw.filter(id => products.some(p => p.id===id)) : []); } catch { saved = new Set(); }
let selectedProduct = null;
let previousFocus = null;
const priceHtml = p => `<span class="price"><small>¥</small>${p.priceValue}<span class="price-unit">${escapeHtml((p.price.match(/\/(.+)/)||[])[1] ? '/'+p.price.match(/\/(.+)/)[1].replace(/（.*$/,'') : '')}</span></span>`;
function syncUrl() {
  const url = new URL(location.href);
  [['category',state.category==='全部好物'?'':state.category],['q',state.query],['sort',state.sort==='original'?'':state.sort],['saved',state.savedOnly?'1':'']].forEach(([key,value]) => value ? url.searchParams.set(key,value) : url.searchParams.delete(key));
  history.replaceState(null,'',url);
}
function render() {
  $('categories').innerHTML = categoryOrder.map(c => `<button class="category" aria-pressed="${state.category===c}" data-category="${c}">${c}<span>${c==='全部好物'?products.length:products.filter(p=>p.category===c).length}</span></button>`).join('');
  const tokens = state.query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  let visible = products.filter(p => (state.category==='全部好物'||p.category===state.category) && (!state.savedOnly||saved.has(p.id)) && tokens.every(token => [p.name,p.brand,p.spec,p.material,p.category,...p.barcodes].join(' ').toLocaleLowerCase().includes(token)));
  if (state.sort!=='original') visible.sort((a,b)=>(a.priceValue-b.priceValue)*(state.sort==='price-up'?1:-1)||a.id-b.id);
  $('result-count').innerHTML = `<span class="result-label${state.savedOnly?' filter-active':''}">${escapeHtml(state.savedOnly?'我的收藏':state.category)}</span><span class="result-total">共 <b>${visible.length}</b> 件好物</span>`;
  $('products').classList.toggle('list',state.view==='list');
  $('products').innerHTML = visible.map((p,i) => `<article class="product"><a class="product-link" href="#product-${p.id}" aria-label="查看${escapeHtml(p.name)}详情"><div class="product-image"><img src="${p.images[0].thumb}" alt="${escapeHtml(p.name)}" width="640" height="640" loading="${i<4?'eager':'lazy'}" decoding="async">${p.images.length>1?`<span class="image-count">${p.images.length} 张图片</span>`:''}</div><div class="product-body"><p class="product-category">${p.category}</p><h2>${escapeHtml(p.shortName)}</h2><p class="product-meta">${escapeHtml(p.material)} / ${escapeHtml(p.spec)}</p><div class="product-bottom">${priceHtml(p)}<span class="detail-hint">查看详情 ${icon('arrow')}</span></div></div></a><button class="favorite" data-save="${p.id}" aria-label="${saved.has(p.id)?'取消收藏':'收藏'}${escapeHtml(p.shortName)}" aria-pressed="${saved.has(p.id)}">${icon('heart')}</button></article>`).join('');
  $('empty').hidden = visible.length>0;
  $('saved-count').textContent = saved.size;
  $('saved-top').setAttribute('aria-pressed',state.savedOnly);
  $('saved-top').setAttribute('aria-label', `${state.savedOnly?'返回全部好物':'只看我的收藏'}，已收藏 ${saved.size} 件`);
  $('grid-view').setAttribute('aria-pressed',state.view==='grid');
  $('list-view').setAttribute('aria-pressed',state.view==='list');
}
function toggleSaved(id) {
  saved.has(id) ? saved.delete(id) : saved.add(id);
  try { localStorage.setItem('zhecheng-favorites',JSON.stringify([...saved])); } catch { /* Browsing remains available if storage is restricted. */ }
  const focusedSave = document.activeElement?.dataset.save;
  render();
  if (focusedSave) document.querySelector(`[data-save="${focusedSave}"]`)?.focus({preventScroll:true});
  if (selectedProduct?.id===id) updateDetailSave();
}
function updateDetailSave() {
  const btn = $('detail-save');
  btn.setAttribute('aria-pressed',saved.has(selectedProduct.id));
  btn.innerHTML = `${icon('heart')}${saved.has(selectedProduct.id)?'已收藏 · 点击取消':'收藏这件好物'}`;
}
function setImage(index) {
  const im = selectedProduct.images[index];
  $('main-photo').src=im.full;
  $('main-photo').alt=`${selectedProduct.name}，第 ${index+1} 张图片`;
  $('original').href=im.full;
  document.querySelectorAll('[data-photo]').forEach(el=>el.setAttribute('aria-pressed',Number(el.dataset.photo)===index));
}
function openDetail(p) {
  if (!$('detail').open) previousFocus=document.activeElement;
  selectedProduct=p;
  $('detail-content').innerHTML=`<div class="detail-layout"><div class="gallery"><img class="main-photo" id="main-photo" src="${p.images[0].full}" alt="${escapeHtml(p.name)}，第 1 张图片"><div class="gallery-tools"><div class="thumbnails" role="group" aria-label="产品图片">${p.images.map((im,i)=>`<button class="thumbnail" data-photo="${i}" aria-label="查看第 ${i+1} 张图片" aria-pressed="${i===0}"><img src="${im.thumb}" alt=""></button>`).join('')}</div><a class="original" id="original" href="${p.images[0].full}" target="_blank" rel="noopener">查看原图 ↗</a></div></div><div class="detail-info"><p class="detail-kicker">${p.category} / ${escapeHtml(p.brand)}</p><h2 id="detail-title">${escapeHtml(p.shortName)}</h2><p class="full-name">${escapeHtml(p.name)}</p><div class="detail-price"><small>¥</small> ${p.priceValue}</div><p class="source-price">清单标价：${escapeHtml(p.price)}</p><dl class="specifications"><div><dt>产品规格</dt><dd>${escapeHtml(p.spec)}</dd></div><div><dt>材质 / 工艺</dt><dd>${escapeHtml(p.material)}</dd></div><div><dt>产品品牌</dt><dd>${escapeHtml(p.brand)}</dd></div><div><dt>产品条码</dt><dd>${p.barcodes.map(escapeHtml).join('\n')}</dd></div></dl><button class="detail-save" id="detail-save"></button></div></div>`;
  updateDetailSave();
  if (!$('detail').open) { $('detail').showModal(); document.body.classList.add('modal-open'); $('close-detail').focus({preventScroll:true}); }
}
function closeDetail(removeHash=true) {
  if (removeHash && /^#product-/.test(location.hash)) history.replaceState(null,'',location.pathname+location.search);
  if ($('detail').open) $('detail').close();
  selectedProduct=null;
  document.body.classList.remove('modal-open');
  if (previousFocus?.isConnected) previousFocus.focus({preventScroll:true});
}
function handleHash() {
  const match = location.hash.match(/^#product-(\d+)$/);
  const p = match && products.find(p=>p.id===Number(match[1]));
  if (p) openDetail(p); else if ($('detail').open) closeDetail(false);
}
$('categories').addEventListener('click',e=>{const btn=e.target.closest('[data-category]');if(!btn)return;state.category=btn.dataset.category;render();syncUrl();$('categories').querySelector(`[data-category="${state.category}"]`)?.focus({preventScroll:true});});
$('search').value=state.query;
$('search').addEventListener('input',e=>{state.query=e.target.value;render();syncUrl();});
$('sort').value=state.sort;
$('sort').addEventListener('change',e=>{state.sort=e.target.value;render();syncUrl();});
$('products').addEventListener('click',e=>{const btn=e.target.closest('[data-save]');if(btn)toggleSaved(Number(btn.dataset.save));});
function toggleSavedOnly(){state.savedOnly=!state.savedOnly;render();syncUrl();}
function closeDisplaySettings(returnFocus=false) {
  $('display-settings').classList.remove('is-open');
  $('display-settings-toggle').setAttribute('aria-expanded','false');
  if (returnFocus) $('display-settings-toggle').focus({preventScroll:true});
}
$('display-settings-toggle').addEventListener('click',()=>{
  const opened=$('display-settings').classList.toggle('is-open');
  $('display-settings-toggle').setAttribute('aria-expanded',opened);
});
document.addEventListener('click',e=>{if(!e.target.closest('#display-settings'))closeDisplaySettings();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('display-settings').classList.contains('is-open')){e.preventDefault();closeDisplaySettings(true);}});
$('saved-top').addEventListener('click',()=>{toggleSavedOnly();$('catalog').scrollIntoView({block:'start'});});
$('grid-view').addEventListener('click',()=>{state.view='grid';render();closeDisplaySettings(true);});
$('list-view').addEventListener('click',()=>{state.view='list';render();closeDisplaySettings(true);});
$('reset').addEventListener('click',()=>{state.category='全部好物';state.query='';state.savedOnly=false;state.sort='original';$('search').value='';$('sort').value='original';render();syncUrl();$('search').focus();});
$('close-detail').addEventListener('click',()=>closeDetail());
$('detail').addEventListener('cancel',e=>{e.preventDefault();closeDetail();});
$('detail').addEventListener('click',e=>{if(e.target===$('detail')){const rect=$('detail').getBoundingClientRect();if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)closeDetail();}const photo=e.target.closest('[data-photo]');if(photo)setImage(Number(photo.dataset.photo));if(e.target.closest('#detail-save'))toggleSaved(selectedProduct.id);});
window.addEventListener('hashchange',handleHash);
window.addEventListener('popstate',()=>{const q=new URLSearchParams(location.search);state.query=q.get('q')||'';state.category=categoryOrder.includes(q.get('category'))?q.get('category'):'全部好物';state.savedOnly=q.get('saved')==='1';state.sort=['price-up','price-down'].includes(q.get('sort'))?q.get('sort'):'original';$('search').value=state.query;$('sort').value=state.sort;render();handleHash();});
render();
handleHash();
