/* ES5 syntax and XMLHttpRequest for iOS 12 Safari. */
(function () {
  'use strict';
  var cfg = window.DASHBOARD_CONFIG || {};
  var features = cfg.features || {};
  var site = cfg.site || {};
  var busy = false;
  function el(id) { return document.getElementById(id); }
  function text(id, value) { var node = el(id); if (node) { node.textContent = value; } }

  function applyConfig() {
    var title = site.title || '桌边控制屏';
    var subtitle = site.subtitle || '';
    document.title = subtitle ? (title + ' · ' + subtitle) : title;
    text('site-title', title);
    text('site-subtitle', subtitle);
    text('host-title', subtitle || '宿主机状态');
    text('site-greeting', site.greeting || '留一块屏，给日常。');

    var showHost = features.host !== false;
    var showDocker = !!features.docker;
    var showNet = !!(features.router || features.proxy);
    var showAihot = features.aihot !== false;
    var showReadhub = features.readhub !== false;
    var showRadio = features.radio !== false;
    var showLinks = !!(features.links && site.links && site.links.length);

    el('machine-section').hidden = !showHost;
    el('docker-section').hidden = !showDocker;
    el('network-section').hidden = !showNet;
    el('aihot-section').hidden = !showAihot;
    el('readhub-section').hidden = !showReadhub;
    el('right-col').hidden = !(showAihot || showReadhub);
    el('radio-bar').hidden = !showRadio;
    el('view-invest').hidden = !showLinks;

    document.body.classList.toggle('no-docker', !showDocker);
    document.body.classList.toggle('no-news', !(showAihot || showReadhub));

    if (showDocker && cfg.docker) {
      text('docker-title', cfg.docker.label || 'Docker 容器');
      var admin = el('docker-admin-link');
      if (cfg.docker.admin_url) {
        admin.href = cfg.docker.admin_url;
        admin.hidden = false;
      } else {
        admin.hidden = true;
      }
    }

    if (showLinks) {
      text('view-invest', site.links_title || '常用入口');
      text('invest-title', site.links_title || '常用入口');
      text('invest-lead', site.links_lead || '');
      var wrap = el('invest-links');
      while (wrap.firstChild) { wrap.removeChild(wrap.firstChild); }
      site.links.forEach(function (item) {
        var card = document.createElement('a');
        card.className = 'invest-card';
        card.href = item.url;
        card.target = '_blank';
        card.rel = 'noopener noreferrer';
        var strong = document.createElement('strong');
        strong.textContent = item.title;
        var span = document.createElement('span');
        span.textContent = item.desc || '';
        var small = document.createElement('small');
        small.textContent = item.domain || '';
        card.appendChild(strong);
        card.appendChild(span);
        card.appendChild(small);
        wrap.appendChild(card);
      });
    }
  }

  function tick() {
    var now = new Date();
    text('clock', ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2));
    text('date', (now.getMonth() + 1) + ' 月 ' + now.getDate() + ' 日 · 星期' + '日一二三四五六'.charAt(now.getDay()));
  }

  function failure() {
    text('connection', '连接中断 · 数据可能已过期');
    text('mac-state', '暂时无法读取本机状态');
    text('docker-state', '暂时无法读取 Docker 状态');
  }

  function refresh() {
    if (features.host === false && !features.docker) {
      text('connection', '面板已就绪');
      text('updated', '时钟运行中');
      return;
    }
    if (busy) { return; }
    busy = true;
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/status', true);
    xhr.timeout = 10000;
    xhr.onload = function () {
      busy = false;
      if (xhr.status !== 200) { failure(); return; }
      try {
        var data = JSON.parse(xhr.responseText);
        var host = data.host || data.mac;
        if (host) {
          text('connection', (host.os_label || '本机') + ' 已连接');
          text('mac-state', '系统在线 · 只读');
          text('disk', host.disk_free_gb + ' GB');
          text('load-label', host.load_label || '系统负载 / 1 分钟');
          text('load-hint', host.load_hint || '');
          text('load', host.load_display === null || typeof host.load_display === 'undefined' ? '—' : host.load_display);
          text('disk-total', host.disk_total_gb + ' GB');
          var mem = host.mem_percent;
          text('mem', mem === null || typeof mem === 'undefined' ? '—' : mem + '%');
          text('mem-note', '内存已用' + (host.mem_total_gb ? ' · ' + host.mem_used_gb + '/' + host.mem_total_gb + ' GB' : ''));
        } else {
          text('connection', '面板已连接');
        }
        text('updated', '最近更新 ' + new Date(data.updated * 1000).toLocaleTimeString() + ' · 每 30 秒更新');
        if (features.docker && data.docker) {
          text('docker-state', data.docker.available
            ? data.docker.containers.filter(function (item) { return item.state === 'running'; }).length + ' 个运行中 / 共 ' + data.docker.containers.length + ' 个容器'
            : data.docker.message);
          var list = el('containers');
          while (list.firstChild) { list.removeChild(list.firstChild); }
          data.docker.containers.forEach(function (item) {
            var li = document.createElement('li');
            var state = document.createElement('span');
            li.appendChild(document.createTextNode(item.name));
            state.textContent = item.status;
            li.appendChild(state); list.appendChild(li);
          });
        }
      } catch (err) { failure(); }
    };
    xhr.onerror = xhr.ontimeout = function () { busy = false; failure(); };
    xhr.send();
  }

  // Give each news list an exact pixel height: iOS 12 compresses flex children
  // until titles are clipped and scrolled rows overlap the tab buttons.
  var layingOut = false;
  function layoutNews() {
    if (layingOut) { return; }
    var right = document.querySelector('.right');
    if (!right || right.hidden) { return; }
    var blocks = right.getElementsByClassName('news');
    if (!blocks.length) { return; }
    layingOut = true;
    var mobile = window.innerWidth <= 700;
    var i;
    for (i = 0; i < blocks.length; i += 1) {
      var block = blocks[i];
      if (block.hidden) { continue; }
      var win = block.getElementsByClassName('news-window')[0];
      if (!win) { continue; }
      win.style.height = '';
      if (mobile) { continue; }
      var avail = block.clientHeight;
      if (!avail) { continue; }
      var used = 0;
      var j;
      for (j = 0; j < block.children.length; j += 1) {
        var child = block.children[j];
        if (child === win) { continue; }
        var style = window.getComputedStyle(child);
        if (style.display === 'none') { continue; }
        used += child.offsetHeight + (parseFloat(style.marginTop) || 0) + (parseFloat(style.marginBottom) || 0);
      }
      avail -= used + (parseFloat(window.getComputedStyle(block).paddingBottom) || 0);
      if (avail > 0) {
        // Snap to whole 46px rows so no row is ever sliced by the block edge.
        var rows = Math.max(2, Math.floor(avail / 46));
        win.style.height = (rows * 46) + 'px';
      }
    }
    layingOut = false;
    if (window.TickerRefit) { window.TickerRefit(); }
  }

  function setView(name) {
    var hasLinks = !!(features.links && site.links && site.links.length);
    var invest = hasLinks && name === 'invest';
    var hasNet = !!(features.router || features.proxy);
    el('invest-view').hidden = !invest;
    el('view-invest').setAttribute('aria-pressed', invest ? 'true' : 'false');
    el('view-home').setAttribute('aria-pressed', invest ? 'false' : 'true');
    el('network-section').hidden = invest || !hasNet;
    document.querySelector('main').hidden = invest;
    document.body.classList[invest ? 'add' : 'remove']('invest-mode');
    try { localStorage.setItem('view', invest ? 'invest' : 'home'); } catch (err) {}
    if (invest) { document.body.scrollTop = 0; window.scrollTo(0, 0); }
    layoutNews();
  }

  function setTheme(name) {
    var night = name === 'night';
    document.documentElement.classList[night ? 'add' : 'remove']('night');
    el('theme-toggle').textContent = night ? '日间' : '夜间';
    el('theme-toggle').setAttribute('aria-pressed', night ? 'true' : 'false');
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', window.getComputedStyle(document.documentElement).getPropertyValue('--bg').trim());
    }
    try { localStorage.setItem('theme', name); } catch (err) {}
    var event = document.createEvent('Event');
    event.initEvent('themechange', false, false);
    window.dispatchEvent(event);
  }

  applyConfig();
  el('view-home').onclick = function () { setView('home'); };
  el('theme-toggle').onclick = function () {
    setTheme(document.documentElement.classList.contains('night') ? 'day' : 'night');
  };
  el('view-invest').onclick = function () { setView('invest'); };
  setTheme(document.documentElement.classList.contains('night') ? 'night' : 'day');
  var savedView = 'home';
  try { savedView = localStorage.getItem('view') === 'invest' ? 'invest' : 'home'; } catch (err) {}
  setView(savedView);
  window.addEventListener('resize', layoutNews, false);
  window.addEventListener('orientationchange', function () { setTimeout(layoutNews, 300); }, false);
  window.addEventListener('load', layoutNews, false);
  el('refresh').onclick = refresh;
  document.addEventListener('visibilitychange', function () { if (!document.hidden) { tick(); refresh(); } });
  tick(); refresh(); layoutNews();
  setInterval(tick, 1000);
  setInterval(function () { if (!document.hidden) { refresh(); } }, 30000);
}());
