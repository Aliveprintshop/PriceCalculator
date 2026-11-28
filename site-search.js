/* =====================================================================
   ALIVE · Site header search for aliveprintshop.com
   (Austin, 2026-11-18; two-line header 2026-11-18 evening)

   Loaded by one <script> tag in the Elementor "Main Header" HTML widget
   (bddddaf). The header's LAYOUT (two lines, like Custom Ink) is CSS in that
   same widget (<style id="aps-header-layout">, copy in
   snippets/wp-header-layout.css) so it is right from the first paint. This
   file adds the pieces: the search bar, the "Talk to a real person" phone
   link, and Contact Us inside the phone menu.

   Desktop (>=1025px):  [logo] [ search ............ ] [phone] [cart]
                        Home Products Services ...   [Contact] [Place order]
   Phone/tablet:        [menu]      [logo]      [cart]
                        [ search .............................. ]

   - Typing shows up to 6 matching products (photo, name, brand, "from"
     price), ranked like the /products/ search. Click one to open it.
   - Enter or "See all results" opens /products/?q=<words>#search-<words>.
   - ON /products/ the header bar is the page's only search: it filters the
     product grid as you type (no dropdown) and the grid hides its own box.

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
  '.aps-sb .aps-sb-x{margin:0!important;padding:0!important;width:30px!important;height:30px!important;min-height:0!important;'+
    'line-height:28px!important;background:transparent!important;border:0!important;box-shadow:none!important;color:#6b7280!important;font-size:20px!important;}'+
  /* the bar in the header (its place in the two lines is set by the header CSS) */
  '.aps-sb-main{margin:0!important;}'+
  '@media(min-width:1025px){.aps-sb-main{flex:1 1 360px!important;max-width:680px!important;min-width:220px!important;}.aps-sb-main .aps-sb-dd{min-width:440px;}}'+
  '@media(max-width:1024px){.aps-sb-main{flex:0 0 100%!important;max-width:none!important;min-width:0!important;}'+
    '.aps-sb-main .aps-sb-in{height:42px!important;line-height:42px!important;font-size:16px!important;}}'+
  '.aps-sb-ghost{pointer-events:none;}'+
  /* "Talk to a real person" (desktop only) */
  '.aps-hphone{display:none;align-items:center;gap:10px;text-decoration:none!important;color:#1e1e1e!important;white-space:nowrap;line-height:1.2;}'+
  '.aps-hphone svg{width:26px;height:26px;flex:none;color:#1e1e1e;}'+
  '.aps-hphone small{display:block;font-size:13px;color:#4b5563;}'+
  '.aps-hphone b{display:block;font-size:15px;font-weight:700;color:#1b6cce;}'+
  '.aps-hphone:hover b{text-decoration:underline;}'+
  '@media(min-width:1025px){.aps-hphone{display:flex;}}'+
  /* Contact Us + call, added under "Place Your Order" in the phone menu */
  '.aps-pop-extra{display:flex;flex-direction:column;gap:12px;margin-top:12px;}'+
  '.aps-pop-extra a{display:flex;align-items:center;justify-content:center;box-sizing:border-box;text-decoration:none!important;}'+
  '.aps-pop-contact{border:1.5px solid #1e1e1e;color:#1e1e1e!important;background:#fff;font-weight:700;}'+
  '.aps-pop-call{color:#1b6cce!important;font-weight:700;font-size:15px;padding:6px 0;}'+
  /* /products/: the header bar is the only search. Hide the page's own phone
     search box and keep Filters + category chips on one line. */
  'body.aps-onesearch #agb-q{display:none!important;}'+
  'body.aps-onesearch #agb{display:flex!important;align-items:center;gap:8px;padding-top:8px!important;padding-bottom:8px!important;}'+
  'body.aps-onesearch #agb .agb-row{flex:none!important;}'+
  'body.aps-onesearch #agb .agb-chips{flex:1 1 auto!important;min-width:0!important;margin:0!important;padding:0!important;}'+
  /* Product pages (/insta-price) on phones and tablets: an app-style header with
     one line (menu, logo, search icon, cart). The search bar opens under it. */
  '.aps-sbtn{display:none;}'+
  '@media(max-width:1024px){'+
    'header.aps-compact .aps-sb-main{display:none!important;}'+
    'header.aps-compact.aps-sopen .aps-sb-main{display:block!important;}'+
    'header.aps-compact .aps-sbtn{display:flex;order:3;flex:0 0 44px;width:44px;height:44px;align-items:center;justify-content:center;'+
      'border:0!important;background:transparent!important;color:#1e1e1e!important;padding:0!important;margin:0!important;cursor:pointer;box-shadow:none!important;}'+
    'header.aps-compact .aps-sbtn svg{width:22px;height:22px;}'+
    'header.aps-compact .elementor-element-bda4dae{flex-basis:88px!important;}}'+
  /* Phones: slimmer price bar on the product page (label and price share a line). */
  '@media(max-width:767px){'+
    '#alive-hostbar .ahb-in{padding:8px 14px!important;}'+
    '#alive-hostbar .ahb-l{display:flex!important;flex-wrap:wrap;align-items:baseline;column-gap:6px;}'+
    '#alive-hostbar .ahb-k{order:2;}'+
    '#alive-hostbar .ahb-v{order:1;}'+
    '#alive-hostbar .ahb-s{order:3;flex-basis:100%;}}';
  /* Product pages: the header slides away while scrolling down and comes back on
     the first scroll up, so the whole product section fits (Austin, 27 Nov 2026). */
  css+='header.aps-hdauto{transition:transform .25s ease,box-shadow .25s ease!important;will-change:transform;}'+
    'header.aps-hdauto.aps-hdhide{transform:translateY(calc(-100% - 12px))!important;box-shadow:none!important;}';
  var st=document.createElement('style');st.textContent=css;document.head.appendChild(st);

  /* ---------------- search engine (copy of index.html) ---------------- */
  var SEARCH_SYNONYMS={
    tee:['t shirt','tshirt'], tshirt:['t shirt','tee'], tshirts:['t shirt','tee'],
    hat:['cap','headwear'], hats:['cap','headwear'], cap:['hat','headwear'],
    caps:['hat','headwear'], beanie:['beanie','knit cap','knit hat','watch cap','toque'], beanies:['beanie','knit cap','knit hat','watch cap','toque'],
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
    if(window.innerWidth<480)input.placeholder='Search t-shirts, hoodies, hats…';
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
    input.addEventListener('focus',function(){if(GRID)return;load();if(input.value.trim())render();});
    input.addEventListener('input',function(){
      clearTimeout(t);
      /* /products/: filter the grid itself, no dropdown */
      if(GRID){w.classList.toggle('has-q',!!input.value.trim());t=setTimeout(function(){gridSearch(input.value);},200);return;}
      t=setTimeout(render,90);
    });
    input.addEventListener('keydown',function(e){
      var o=opts();
      if(e.key==='ArrowDown'&&o.length){e.preventDefault();setSel(Math.min(sel+1,o.length-1));}
      else if(e.key==='ArrowUp'&&o.length){e.preventDefault();setSel(Math.max(sel-1,0));}
      else if(e.key==='Escape'){close();input.blur();}
      else if(e.key==='Enter'&&sel>-1&&o[sel]){e.preventDefault();o[sel].click();}
    });
    form.addEventListener('submit',function(e){
      e.preventDefault();var q=input.value.trim();
      if(GRID){clearTimeout(t);gridSearch(input.value);input.blur();scrollToGrid();if(q)track('search',{search_term:q,source:'header_products'});return;}
      if(!q)return;
      track('search',{search_term:q,source:'header'});
      window.location.href=resultsUrl(q);
    });
    w.querySelector('.aps-sb-x').addEventListener('click',function(){input.value='';if(GRID){w.classList.remove('has-q');gridSearch('');}else render();input.focus();});
    dd.addEventListener('mousedown',function(e){e.preventDefault();});   /* keep focus while clicking */
    dd.addEventListener('click',function(e){
      var a=e.target.closest&&e.target.closest('.aps-sb-it');
      if(a)track('select_item',{item_id:a.getAttribute('data-s'),source:'header_search',search_term:input.value.trim()});
    });
    document.addEventListener('click',function(e){if(!w.contains(e.target))close();});
    input.addEventListener('blur',function(){setTimeout(function(){if(!w.contains(document.activeElement))close();},150);});
    /* Keep the words in the box on the products page so shoppers can refine. */
    try{var pq=new URLSearchParams(location.search).get('q');if(pq&&/^\/products/.test(location.pathname)){input.value=pq;w.classList.add('has-q');}}catch(e){}
    INPUTS.push(input);
    return w;
  }

  /* ---------------- /products/: drive the product grid ---------------- */
  var GRID=null,GRID_ORIGIN='https://aliveprintshop.github.io',INPUTS=[];
  var PRODUCT_PAGE=/^\/insta-price/.test(location.pathname)||!!document.querySelector('iframe[src*="alive-product"]');
  function gridSend(m){try{GRID.contentWindow.postMessage(m,GRID_ORIGIN);}catch(e){}}
  function gridSearch(q){gridSend({type:'alive-grid-search',q:q});}
  function scrollToGrid(){
    try{var hd=document.querySelector('header.elementor-element-92c3014:not(.elementor-sticky__spacer)');
      var top=GRID.getBoundingClientRect().top+window.pageYOffset-(hd?hd.getBoundingClientRect().bottom:0)-8;
      if(window.pageYOffset>top)window.scrollTo({top:Math.max(0,top),behavior:'smooth'});}catch(e){}
  }
  function gridSetup(){
    GRID=document.getElementById('alive-frame');
    if(!GRID)return;
    document.body.classList.add('aps-onesearch');
    function hello(){gridSend({type:'alive-ext-search'});}
    hello();GRID.addEventListener('load',hello);
    window.addEventListener('message',function(e){
      if(e.origin!==GRID_ORIGIN)return;var d=e.data||{};
      if(d.type==='alive-gridready')hello();
      /* the grid reports its search words (e.g. cleared by a category chip): show them in the bar */
      if(d.type==='alive-gridmodel'&&d.model&&typeof d.model.q==='string'){
        INPUTS.forEach(function(i){if(document.activeElement!==i&&i.value!==d.model.q){i.value=d.model.q;
          var w=i.closest('.aps-sb');if(w)w.classList.toggle('has-q',!!d.model.q.trim());}});
      }
    },false);
  }

  /* ---------------- phone link ---------------- */
  var HEADSET='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="2.5" y="13" width="4" height="6" rx="1.5"/><rect x="17.5" y="13" width="4" height="6" rx="1.5"/><path d="M19.5 19c0 1.5-1.5 2.5-4 2.5h-2"/></svg>';
  function phone(){
    var a=document.createElement('a');a.className='aps-hphone';a.href='tel:+17026856270';
    a.innerHTML=HEADSET+'<span><small>Talk to a real person</small><b>702-685-6270</b></span>';
    a.addEventListener('click',function(){track('click_call',{source:'header'});});
    return a;
  }

  /* ---------------- place them in the header ---------------- */
  function mount(){
    var headers=document.querySelectorAll('header.elementor-element-92c3014');
    var done=0;
    headers.forEach(function(hd){
      if(hd.querySelector('.aps-sb'))return;
      var ghost=hd.classList.contains('elementor-sticky__spacer');   /* invisible copy that holds the page's place */
      var logo=hd.querySelector('.elementor-widget-image, .elementor-widget-theme-site-logo');
      if(!logo||!logo.parentNode)return;
      var bar;
      if(ghost){bar=document.createElement('div');bar.className='aps-sb aps-sb-main aps-sb-ghost';bar.setAttribute('aria-hidden','true');
        bar.innerHTML='<form><input class="aps-sb-in" type="text" tabindex="-1"></form>';}
      else bar=build('aps-sb-main');
      logo.parentNode.insertBefore(bar,logo.nextSibling);
      var cart=hd.querySelector('.elementor-element-c9fb1e4');
      var ph=phone();if(ghost){ph.setAttribute('aria-hidden','true');ph.tabIndex=-1;}
      if(cart&&cart.parentNode)cart.parentNode.insertBefore(ph,cart);else bar.parentNode.insertBefore(ph,bar.nextSibling);
      if(PRODUCT_PAGE){
        hd.classList.add('aps-compact');
        if(!ghost){
          var sb=document.createElement('button');sb.type='button';sb.className='aps-sbtn';sb.setAttribute('aria-label','Search products');sb.setAttribute('aria-expanded','false');
          sb.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/></svg>';
          sb.addEventListener('click',function(){var open=!hd.classList.contains('aps-sopen');hd.classList.toggle('aps-sopen',open);sb.setAttribute('aria-expanded',open?'true':'false');
            if(open){var i=hd.querySelector('.aps-sb-main input');if(i)setTimeout(function(){i.focus();},0);}});
          if(cart&&cart.parentNode)cart.parentNode.insertBefore(sb,cart);
        }
      }
      hd.classList.add('aps-hready');
      done++;
    });
    return done;
  }

  /* ---------------- phone menu: add Contact Us + call ---------------- */
  function popupExtras(){
    var pm=document.getElementById('elementor-popup-modal-101');
    if(!pm||pm.querySelector('.aps-pop-extra'))return;
    var btn=null;pm.querySelectorAll('a.elementor-button').forEach(function(a){if(!btn&&/place your order/i.test(a.textContent))btn=a;});
    if(!btn)return;
    var wid=btn.closest('.elementor-widget')||btn.parentNode;
    var cs=getComputedStyle(btn),x=document.createElement('div');x.className='aps-pop-extra';
    x.innerHTML='<a class="aps-pop-contact" href="/contact-us/">Contact Us</a><a class="aps-pop-call" href="tel:+17026856270">Call 702-685-6270</a>';
    var c=x.firstChild;c.style.height=btn.offsetHeight+'px';c.style.borderRadius=cs.borderRadius;c.style.fontSize=cs.fontSize;c.style.fontFamily=cs.fontFamily;
    wid.parentNode.insertBefore(x,wid.nextSibling);
    x.querySelector('.aps-pop-call').addEventListener('click',function(){track('click_call',{source:'phone_menu'});});
  }
  function watchPopup(){
    if(window.jQuery)window.jQuery(document).on('elementor/popup/show',function(){setTimeout(popupExtras,0);});
    document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('.elementor-element-bda4dae');if(a)setTimeout(popupExtras,450);},true);
  }

  /* ---------------- phones: the home page buttons read "Get Started →" ---------------- */
  function mobileCta(){
    var els=document.querySelectorAll('.elementor-element-a92765d .elementor-button-text, .elementor-element-46f7cda .elementor-button-text');
    if(!els.length||!window.matchMedia)return;
    var mq=window.matchMedia('(max-width: 767px)');
    function apply(){els.forEach(function(t){if(t.dataset.apsOrig==null)t.dataset.apsOrig=t.textContent;t.textContent=mq.matches?'Get Started \u2192':t.dataset.apsOrig;});}
    apply();if(mq.addEventListener)mq.addEventListener('change',apply);
  }

  /* ---------------- cart count on the header bag (Austin, 20 Nov 2026) ----------------
     The cart lives in the github.io pages' storage, which this page can't read.
     The product and cart pages post {type:'alive-cart-count', n} up to us; we keep
     the last number here so every page (home, /products/ …) can show it. */
  var CC_KEY='aps_cart_count';
  function ccGet(){try{return Math.max(0,parseInt(localStorage.getItem(CC_KEY)||'0',10)||0);}catch(e){return 0;}}
  function ccDraw(){
    var n=ccGet();
    document.querySelectorAll('.elementor-element-c9fb1e4 a.elementor-icon').forEach(function(a){
      var b=a.querySelector('.aps-cc');
      if(!n){if(b)b.remove();a.setAttribute('aria-label','Cart');return;}
      if(!b){b=document.createElement('span');b.className='aps-cc';b.setAttribute('aria-hidden','true');a.appendChild(b);}
      b.textContent=n>99?'99+':String(n);
      a.setAttribute('aria-label','Cart, '+n+' item'+(n===1?'':'s'));
    });
  }
  (function(){
    var st=document.createElement('style');
    st.textContent='.elementor-element-c9fb1e4 a.elementor-icon{position:relative;}'+
      '.aps-cc{position:absolute;top:-7px;right:-7px;min-width:19px;height:19px;padding:0 5px;border-radius:999px;background:#1B6CCE;color:#fff;'+
      'font:800 11px/19px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;text-align:center;box-sizing:border-box;pointer-events:none;'+
      'box-shadow:0 0 0 2px #fff;}';
    document.head.appendChild(st);
    window.addEventListener('message',function(e){
      if(e.origin!=='https://aliveprintshop.github.io')return;
      var d=e.data;if(!d||d.type!=='alive-cart-count')return;
      var n=Math.max(0,parseInt(d.n,10)||0);
      try{localStorage.setItem(CC_KEY,String(n));}catch(x){}
      ccDraw();
    });
    window.addEventListener('storage',function(e){if(e.key===CC_KEY)ccDraw();});
  })();

  /* ---------------- product pages: hide the header on scroll down ---------------- */
  function autoHideHeader(){
    if(!PRODUCT_PAGE)return;
    var lastY=window.pageYOffset,acc=0,ticking=false;
    function hd(){return document.querySelector('header.elementor-element-92c3014:not(.elementor-sticky__spacer)');}
    function busy(h){
      /* never hide while the customer is using the header: search open, typing, a menu open or hovered */
      return h.classList.contains('aps-sopen')||h.contains(document.activeElement)||h.matches(':hover')||
        !!h.querySelector('.aps-sb.open');
    }
    function step(){
      ticking=false;
      var h=hd();if(!h)return;
      h.classList.add('aps-hdauto');
      var y=window.pageYOffset,d=y-lastY;lastY=y;
      var hh=h.offsetHeight||130;
      if(y<=hh){h.classList.remove('aps-hdhide');acc=0;return;}
      acc=(d>0)===(acc>0)?acc+d:d;           /* distance moved in the current direction */
      if(acc>12&&!busy(h))h.classList.add('aps-hdhide');
      else if(acc<-8)h.classList.remove('aps-hdhide');
    }
    window.addEventListener('scroll',function(){if(!ticking){ticking=true;requestAnimationFrame(step);}},{passive:true});
    /* the pointer heading for the top edge brings it back too (desktop) */
    document.addEventListener('mousemove',function(e){if(e.clientY<24){var h=hd();if(h)h.classList.remove('aps-hdhide');}},{passive:true});
  }

  function boot(){
    gridSetup();watchPopup();mobileCta();autoHideHeader();
    ccDraw();setTimeout(ccDraw,600);setTimeout(ccDraw,2000);
    if(!mount()){var n=0,iv=setInterval(function(){if(mount()||++n>40)clearInterval(iv);},250);}
    /* Elementor makes the invisible copy of a sticky header a moment later */
    setTimeout(mount,600);setTimeout(mount,2000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
