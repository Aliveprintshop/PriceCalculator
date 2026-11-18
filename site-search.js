/* =====================================================================
   ALIVE · Header search bar for aliveprintshop.com (Austin, 2026-11-18)

   Loaded by one <script> tag in the Elementor "Main Header" HTML widget
   (bddddaf). Everything else lives here, so changes ship with a normal
   GitHub upload and no WordPress edit.

   - Desktop (>=1025px): a search bar between the logo and the menu.
   - Phone/tablet: a full-width bar under the header row.
   - Typing shows up to 6 matching products (photo, name, brand, "from"
     price), ranked like the /products/ search. Click one to open it.
   - Enter or "See all results" opens /products/?q=<words>#search-<words>,
     which the products grid turns into the same search.

   Data: search-index.json (built by split-products.py on every publish),
   fetched the first time the shopper focuses the box.
   The matching and scoring below are a copy of index.html's search
   (_searchTokens / _matchSearch / _searchScore / SEARCH_SYNONYMS).
   Keep the two in sync.
   ===================================================================== */
(function(){
  if(window.__apsSearch)return; window.__apsSearch=true;
  var BASE='https://aliveprintshop.github.io/PriceCalculator/';
  var INDEX_URL=BASE+'search-index.json';
  var PRODUCT_URL='/insta-price/?style=';
  var MAX=6;

  /* ---------------- styles ---------------- */
  var css=''+
  '.aps-sb{position:relative;flex:1 1 360px;min-width:180px;max-width:520px;margin:0 18px;font-family:inherit;}'+
  '.aps-sb form{margin:0;}'+
  /* !important: the theme styles every input[type=search]. */
  '.aps-sb .aps-sb-in{width:100%!important;box-sizing:border-box!important;height:44px!important;margin:0!important;'+
    'border:1px solid #e3e7ec!important;background:#f2f4f7!important;border-radius:999px!important;'+
    'padding:0 44px 0 42px!important;font-size:15px!important;line-height:44px!important;color:#1e1e1e!important;outline:none!important;'+
    'box-shadow:none;-webkit-appearance:none;appearance:none;transition:border-color .15s,background .15s,box-shadow .15s;}'+
  '.aps-sb .aps-sb-in::placeholder{color:#6b7280;opacity:1;}'+
  '.aps-sb .aps-sb-in::-webkit-search-cancel-button{display:none;}'+
  '.aps-sb .aps-sb-in:focus{background:#fff!important;border-color:#1b6cce!important;box-shadow:0 0 0 3px rgba(27,108,206,.15)!important;}'+
  '.aps-sb-ic{position:absolute;left:15px;top:50%;transform:translateY(-50%);width:18px;height:18px;pointer-events:none;color:#4b5563;}'+
  '.aps-sb-x{position:absolute;right:8px;top:50%;transform:translateY(-50%);width:30px;height:30px;border:0;border-radius:50%;'+
    'background:transparent;color:#6b7280;font-size:20px;line-height:30px;cursor:pointer;display:none;padding:0;}'+
  '.aps-sb.has-q .aps-sb-x{display:block;}'+
  '.aps-sb-dd{position:absolute;left:0;right:0;top:calc(100% + 6px);background:#fff;border:1px solid #e3e7ec;border-radius:14px;'+
    'box-shadow:0 14px 34px rgba(16,24,40,.16);overflow:hidden;z-index:99999;display:none;text-align:left;}'+
  '.aps-sb.open .aps-sb-dd{display:block;}'+
  '.aps-sb-it{display:flex;align-items:center;gap:12px;padding:9px 14px;text-decoration:none!important;color:#1e1e1e!important;cursor:pointer;}'+
  '.aps-sb-it:hover,.aps-sb-it.on{background:#f2f6fc;}'+
  '.aps-sb-im{flex:0 0 52px;width:52px;height:52px;border-radius:8px;background:#fff;border:1px solid #eef0f3;object-fit:contain;}'+
  '.aps-sb-tx{flex:1;min-width:0;}'+
  '.aps-sb-nm{font-size:14px;font-weight:600;line-height:1.25;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;}'+
  '.aps-sb-br{font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#1b6cce;margin-bottom:2px;}'+
  '.aps-sb-pr{flex:0 0 auto;font-size:12.5px;color:#4b5563;white-space:nowrap;}'+
  '.aps-sb-pr b{color:#1e1e1e;font-size:14px;}'+
  '.aps-sb-all{display:block;padding:12px 14px;border-top:1px solid #eef0f3;font-size:14px;font-weight:700;color:#1b6cce!important;'+
    'text-decoration:none!important;cursor:pointer;}'+
  '.aps-sb-all:hover,.aps-sb-all.on{background:#f2f6fc;}'+
  '.aps-sb-msg{padding:14px;font-size:14px;color:#4b5563;}'+
  /* phone row */
  '.aps-sb-row{display:none;width:100%;box-sizing:border-box;padding:0 14px 12px;}'+
  '.aps-sb-row .aps-sb{margin:0;max-width:none;flex:none;}'+
  '@media(max-width:1024px){.aps-sb-desk{display:none!important;}.aps-sb-row{display:block;}'+
    'header.aps-sb-host{flex-wrap:wrap!important;}}'+
  '@media(min-width:1321px){.aps-sb-row{display:none!important;}}'+
  '.aps-sb .aps-sb-x{margin:0!important;padding:0!important;width:30px!important;height:30px!important;min-height:0!important;'+
    'line-height:28px!important;background:transparent!important;border:0!important;box-shadow:none!important;color:#6b7280!important;font-size:20px!important;}'+
  '.aps-sb-desk .aps-sb-dd{min-width:440px;}'+
  /* Desktop header layout with the bar in it: the right-hand buttons take only
     the room they need, the menu never shrinks (it would overlap the cart), and
     the bar takes what is left. The header's content column is 1440px here
     (1312px + room for the bar). */
  '@media(min-width:1321px){'+
    'header.aps-sb-host.elementor-element-92c3014{padding-left:max(32px,calc((100% - 1440px) / 2))!important;padding-right:max(32px,calc((100% - 1440px) / 2))!important;}'+
    'header.aps-sb-host .elementor-element-08286aa{width:auto!important;flex:0 0 auto!important;}'+
    'header.aps-sb-host .elementor-element-645e597{flex:1 1 auto!important;width:auto!important;min-width:0!important;gap:24px!important;}'+
    'header.aps-sb-host .elementor-widget-nav-menu{flex:0 0 auto!important;}'+
    '.aps-sb-desk{flex:1 1 300px!important;min-width:200px!important;max-width:560px!important;margin:0!important;}}'+
  /* Narrow desktops (no room in the row): use the full-width bar under the header. */
  '@media(min-width:1025px) and (max-width:1320px){.aps-sb-desk{display:none!important;}'+
    '.aps-sb-row{display:block!important;}.aps-sb-row .aps-sb{max-width:640px;margin:0 auto;}'+
    'header.aps-sb-host{flex-wrap:wrap!important;}}';
  var st=document.createElement('style');st.textContent=css;document.head.appendChild(st);

  /* ---------------- search engine (copy of index.html) ---------------- */
  var SEARCH_SYNONYMS={
    tee:['t shirt','tshirt'], tshirt:['t shirt','tee'], tshirts:['t shirt','tee'],
    hat:['cap','headwear'], hats:['cap','headwear'], cap:['hat','headwear'],
    caps:['hat','headwear'], beanie:['beanie','knit cap'], beanies:['beanie','knit cap'],
    trucker:['mesh back','trucker'],
    hoodie:['hooded','hoodie'], hoodies:['hooded','hoodie'],
    hoody:['hooded','hoodie'], sweatshirt:['sweatshirt','fleece'],
    crewneck:['crew neck','sweatshirt'],
    quarterzip:['1 4 zip','quarter zip'], halfzip:['1 2 zip','half zip'],
    jacket:['outerwear','jacket'], jackets:['outerwear','jacket'],
    coat:['jacket','outerwear'], vest:['vest','bodywarmer'],
    softshell:['soft shell'], windbreaker:['wind','jacket'],
    polo:['knit','sport shirt'], polos:['knit','sport shirt'],
    jogger:['sweatpant','jogger'], joggers:['sweatpant','jogger'],
    sweatpants:['sweatpant','jogger'], shorts:['short'],
    longsleeve:['long sleeve'], tank:['tank top','sleeveless'],
    drifit:['dri fit','moisture','performance'], dryfit:['dri fit','moisture','performance'],
    wicking:['moisture','performance','dri fit'],
    performance:['moisture','polyester','dri fit'],
    waterproof:['water resistant','waterproof'], rain:['water resistant','waterproof'],
    womens:['women s','ladies','women'], ladies:['women s','ladies','women'],
    women:['women s','ladies'], mens:['men s','men'],
    kids:['youth','toddler'], kid:['youth','toddler'], child:['youth','toddler'],
    bag:['backpack','tote','duffel','pack','bag'], bags:['backpack','tote','duffel','pack','bag'],
    backpack:['pack','backpack'], duffel:['duffle','duffel'], duffle:['duffel','duffle'],
    safety:['hi vis','high visibility','ansi','safety'],
    hivis:['hi vis','high visibility'], reflective:['reflective','hi vis'],
    fleece:['fleece'], flannel:['flannel','plaid'],
    organic:['organic'], recycled:['recycled','sustainable'], sustainable:['recycled','sustainable'],
    cotton:['cotton'], poly:['polyester'], tri:['triblend','tri blend'],
    triblend:['tri blend','triblend'], blend:['blend'],
    vneck:['v neck'], henley:['henley','placket'],
    apron:['apron'],
    workwear:['work','duck','canvas'], scrub:['scrub','medical'],
    eco:['recycled','organic','sustainable']
  };
  function norm(s){return String(s||'').toLowerCase().replace(/[^a-z0-9]+/g,' ');}
  function tokens(q){
    q=norm(q).trim();
    var raw=q?q.split(/\s+/):[];
    if(raw.length>1)raw=raw.filter(function(t){return t.length>1;});
    return raw.map(function(t){
      var alts=[t],syn=SEARCH_SYNONYMS[t];
      if(syn)syn.forEach(function(s){alts.push(norm(s));});
      return alts;
    });
  }
  function prep(it){
    if(it._f)return it._f;
    it._f={style:norm(it.s),brand:norm(it.b),name:norm(it.n),cat:norm(it.c),desc:norm(it.d),colors:norm(it.k)};
    it._h=(it._f.brand+' '+it._f.style+' '+it._f.name+' '+it._f.cat+' '+it._f.desc+' '+it._f.colors).replace(/\s+/g,' ');
    return it._f;
  }
  function matches(it,toks){
    prep(it);
    for(var i=0;i<toks.length;i++){
      var ok=false;
      for(var j=0;j<toks[i].length;j++){var a=toks[i][j];if(a&&it._h.indexOf(a)>-1){ok=true;break;}}
      if(!ok)return false;
    }
    return true;
  }
  function score(it,toks,phrase){
    var f=prep(it),sc=0;
    if(f.style===phrase)sc+=1000;else if(phrase&&f.style.indexOf(phrase)>-1)sc+=400;
    if(phrase&&f.name.indexOf(phrase)>-1)sc+=250;
    if(phrase&&f.brand.indexOf(phrase)>-1)sc+=150;
    toks.forEach(function(alts){
      var n=0,b=0,c=0,k=0,d=0;
      alts.forEach(function(a){if(!a)return;
        if(f.name.indexOf(a)>-1)n=1;if(f.brand.indexOf(a)>-1)b=1;if(f.cat.indexOf(a)>-1)c=1;
        if(f.colors.indexOf(a)>-1)k=1;if(f.desc.indexOf(a)>-1)d=1;});
      sc+=n*60+b*40+c*25+k*12+d*3;
    });
    return sc;
  }
  function search(q){
    var toks=tokens(q);if(!toks.length||!ITEMS)return {list:[],total:0};
    var phrase=norm(q).trim(),hits=[];
    for(var i=0;i<ITEMS.length;i++){var it=ITEMS[i];if(matches(it,toks))hits.push({it:it,sc:score(it,toks,phrase),i:i});}
    hits.sort(function(a,b){return b.sc-a.sc||a.i-b.i;});
    return {list:hits.slice(0,MAX).map(function(h){return h.it;}),total:hits.length};
  }

  /* ---------------- data ---------------- */
  var ITEMS=null,loading=null;
  function load(){
    if(ITEMS||loading)return loading;
    loading=fetch(INDEX_URL,{cache:'default'}).then(function(r){return r.ok?r.json():{items:[]};})
      .then(function(j){ITEMS=(j&&j.items)||[];return ITEMS;})
      .catch(function(){ITEMS=[];return ITEMS;});
    return loading;
  }

  /* ---------------- helpers ---------------- */
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];});}
  function cleanName(n,b){
    n=String(n||'');if(!b)return n;
    var bb=b.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    return n.replace(new RegExp('^\\s*'+bb+'\\s*[\\-\\.\\:\\u2014]?\\s*','i'),'').trim();
  }
  function resultsUrl(q){
    var slug=norm(q).trim().replace(/\s+/g,'-');
    return '/products/?q='+encodeURIComponent(q.trim())+'#search-'+slug;
  }
  function track(ev,params){try{if(window.gtag)window.gtag('event',ev,params||{});}catch(e){}}

  /* ---------------- one search box ---------------- */
  var SVG='<svg class="aps-sb-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/></svg>';
  function build(extraClass){
    var w=document.createElement('div');
    w.className='aps-sb '+(extraClass||'');
    w.innerHTML='<form role="search" action="/products/" autocomplete="off">'+SVG+
      '<input class="aps-sb-in" type="search" name="q" placeholder="Search t-shirts, hoodies, hats and more" aria-label="Search products" autocomplete="off" enterkeyhint="search">'+
      '<button type="button" class="aps-sb-x" aria-label="Clear search">&times;</button></form>'+
      '<div class="aps-sb-dd" role="listbox"></div>';
    var input=w.querySelector('input'),dd=w.querySelector('.aps-sb-dd'),form=w.querySelector('form');
    var sel=-1,t=null;
    function opts(){return dd.querySelectorAll('.aps-sb-it,.aps-sb-all');}
    function setSel(i){var o=opts();sel=i;for(var k=0;k<o.length;k++)o[k].classList.toggle('on',k===i);}
    function close(){w.classList.remove('open');sel=-1;}
    function render(){
      var q=input.value;w.classList.toggle('has-q',!!q.trim());
      if(!q.trim()){dd.innerHTML='';close();return;}
      if(!ITEMS){dd.innerHTML='<div class="aps-sb-msg">Searching…</div>';w.classList.add('open');
        load().then(function(){if(input.value===q)render();});return;}
      var r=search(q);sel=-1;
      if(!r.total){dd.innerHTML='<div class="aps-sb-msg">No products match “'+esc(q.trim())+'”. Try a style number or a simpler word like “hoodie”.</div>';w.classList.add('open');return;}
      var h=r.list.map(function(it){
        return '<a class="aps-sb-it" role="option" href="'+PRODUCT_URL+encodeURIComponent(it.s)+'" data-s="'+esc(it.s)+'">'+
          (it.i?'<img class="aps-sb-im" src="'+esc(it.i)+'" alt="" loading="lazy">':'<span class="aps-sb-im"></span>')+
          '<span class="aps-sb-tx">'+(it.b?'<span class="aps-sb-br">'+esc(it.b)+'</span>':'')+
          '<span class="aps-sb-nm">'+esc(cleanName(it.n,it.b))+'</span></span>'+
          (it.p!=null?'<span class="aps-sb-pr">from <b>$'+Number(it.p).toFixed(2)+'</b></span>':'')+'</a>';
      }).join('');
      h+='<a class="aps-sb-all" href="'+resultsUrl(q)+'">See all '+r.total.toLocaleString()+' results for “'+esc(q.trim())+'” &rarr;</a>';
      dd.innerHTML=h;w.classList.add('open');
    }
    input.addEventListener('focus',function(){load();if(input.value.trim())render();});
    input.addEventListener('input',function(){clearTimeout(t);t=setTimeout(render,90);});
    input.addEventListener('keydown',function(e){
      var o=opts();
      if(e.key==='ArrowDown'&&o.length){e.preventDefault();setSel(Math.min(sel+1,o.length-1));}
      else if(e.key==='ArrowUp'&&o.length){e.preventDefault();setSel(Math.max(sel-1,0));}
      else if(e.key==='Escape'){close();input.blur();}
      else if(e.key==='Enter'&&sel>-1&&o[sel]){e.preventDefault();o[sel].click();}
    });
    form.addEventListener('submit',function(e){
      e.preventDefault();var q=input.value.trim();if(!q)return;
      track('search',{search_term:q,source:'header'});
      window.location.href=resultsUrl(q);
    });
    w.querySelector('.aps-sb-x').addEventListener('click',function(){input.value='';render();input.focus();});
    dd.addEventListener('mousedown',function(e){e.preventDefault();});   /* keep focus while clicking */
    dd.addEventListener('click',function(e){
      var a=e.target.closest&&e.target.closest('.aps-sb-it');
      if(a)track('select_item',{item_id:a.getAttribute('data-s'),source:'header_search',search_term:input.value.trim()});
    });
    document.addEventListener('click',function(e){if(!w.contains(e.target))close();});
    input.addEventListener('blur',function(){setTimeout(function(){if(!w.contains(document.activeElement))close();},150);});
    /* Keep the words in the box on the products page so shoppers can refine. */
    try{var pq=new URLSearchParams(location.search).get('q');if(pq&&/^\/products/.test(location.pathname)){input.value=pq;w.classList.add('has-q');}}catch(e){}
    return w;
  }

  /* ---------------- place it in the header ---------------- */
  function mount(){
    var headers=document.querySelectorAll('header.elementor-element-92c3014, [data-elementor-type="header"] header');
    if(!headers.length)headers=document.querySelectorAll('header');
    var done=0;
    headers.forEach(function(hd){
      if(hd.querySelector('.aps-sb'))return;
      if(hd.classList.contains('elementor-sticky__spacer'))return;   /* invisible clone */
      /* Desktop: between the logo and the menu. */
      var logo=hd.querySelector('.elementor-widget-image, .elementor-widget-theme-site-logo');
      if(logo&&logo.parentNode){
        var d=build('aps-sb-desk');
        logo.parentNode.insertBefore(d,logo.nextSibling);
        logo.parentNode.style.flexWrap='nowrap';
      }
      /* Phone/tablet: a full-width row under the header. */
      var r=document.createElement('div');r.className='aps-sb-row';r.appendChild(build('aps-sb-mob'));
      hd.appendChild(r);
      hd.classList.add('aps-sb-host');   /* lets the phone row wrap under the header */
      done++;
    });
    return done;
  }
  function boot(){if(!mount()){var n=0,iv=setInterval(function(){if(mount()||++n>40)clearInterval(iv);},250);}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
