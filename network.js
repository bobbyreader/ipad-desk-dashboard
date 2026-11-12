/* Canvas 2D, ES5 and XHR: no WebGL, external tiles or tracking services. */
(function () {
  'use strict';
  var cfg = window.DASHBOARD_CONFIG || {};
  var features = cfg.features || {};
  var hasRouter = !!features.router;
  var hasProxy = !!features.proxy;
  if (!hasRouter && !hasProxy) { return; }

  var routerCfg = cfg.router || {};
  var proxyCfg = cfg.proxy || {};
  var routerIface = routerCfg.interface || 'eth0';
  var routerLabel = routerCfg.source_label || '旁路由';
  var proxyName = proxyCfg.label || 'Mihomo';
  var proxyHostLabel = proxyCfg.source_label || '代理核心';

  var canvas = document.getElementById('world-map');
  var ctx = canvas.getContext('2d');
  var chart = document.getElementById('traffic-chart');
  var plot = chart.getContext('2d');
  var current = null, latest = null, pending = false, lastFrame = 0, lastSuccess = 0, lastHistory = [];
  var source = hasRouter ? 'router' : 'proxy', selectedDevice = null, requestGeneration = 0;
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  var origin = [104, 35];
  var land = [
    [[-168,71],[-149,70],[-137,60],[-128,54],[-124,43],[-117,32],[-106,24],[-98,17],[-88,16],[-83,9],[-78,9],[-84,19],[-80,25],[-81,31],[-75,35],[-66,44],[-60,49],[-68,56],[-81,62],[-96,67],[-113,71],[-136,69]],
    [[-73,59],[-48,60],[-25,73],[-40,82],[-62,81]],
    [[-81,12],[-71,11],[-61,7],[-50,1],[-35,-7],[-39,-20],[-48,-29],[-54,-37],[-68,-55],[-75,-49],[-74,-30],[-81,-6]],
    [[-11,36],[-10,44],[-1,49],[6,54],[8,58],[5,62],[18,71],[29,70],[32,59],[47,67],[70,73],[100,77],[132,71],[160,69],[179,65],[167,57],[151,51],[144,42],[135,35],[124,39],[121,30],[113,22],[109,17],[106,8],[100,2],[98,15],[90,22],[80,8],[73,20],[66,25],[57,25],[50,15],[43,12],[36,30],[26,40],[19,40],[15,36],[10,44],[3,42],[-5,36]],
    [[-17,32],[-6,36],[10,37],[25,32],[33,30],[36,20],[44,11],[51,12],[43,-2],[40,-15],[33,-26],[20,-35],[13,-28],[10,-10],[1,4],[-8,5],[-17,15]],
    [[113,-22],[114,-34],[131,-32],[140,-38],[151,-34],[153,-25],[145,-14],[136,-12],[130,-14],[122,-17]],
    [[166,-35],[178,-39],[171,-46],[166,-46]],
    [[129,31],[135,34],[141,41],[145,44],[143,36],[136,32]],
    [[-8,50],[-6,58],[0,59],[2,52]],
    [[47,-13],[50,-17],[47,-25],[44,-24]],
    [[96,5],[103,1],[106,-6],[113,-8],[119,-8],[112,-5],[105,-3]],
    [[109,7],[118,6],[119,-3],[111,-4]],
    [[120,19],[124,17],[126,7],[123,6]],
    [[132,-3],[142,-3],[151,-10],[141,-9]]
  ];
  function text(id, value) { document.getElementById(id).textContent = value; }
  function point(pair) { return [24 + (pair[0] + 180) / 360 * 952, 20 + (82 - pair[1]) / 140 * 390]; }
  function bytes(value) {
    if (value === null || typeof value !== 'number') { return '—'; }
    var units = ['B', 'KB', 'MB', 'GB', 'TB'], n = 0;
    while (value >= 1024 && n < units.length - 1) { value /= 1024; n++; }
    return value.toFixed(n ? 1 : 0) + ' ' + units[n];
  }
  function rate(value) { return value === null ? '采样中' : bytes(value) + '/s'; }

  var palette = {};
  function readPalette() {
    var style = window.getComputedStyle(document.documentElement);
    var read = function (name) { return style.getPropertyValue(name).trim(); };
    palette = {
      sea: read('--sea'), grid: read('--grid'), land: read('--land'), coast: read('--coast'),
      accent: read('--accent'), accent2: read('--accent-2'), inactive: read('--inactive'),
      text: read('--text'), text2: read('--text-2'), dot: read('--dot'), line: read('--line')
    };
  }

  function baseMap() {
    ctx.clearRect(0, 0, 1000, 440);
    ctx.fillStyle = palette.sea; ctx.fillRect(0, 0, 1000, 440);
    ctx.lineWidth = 0.7; ctx.strokeStyle = palette.grid;
    var x, y;
    for (x = -180; x <= 180; x += 30) {
      var p = point([x, 80]), q = point([x, -55]);
      ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke();
    }
    for (y = -30; y <= 60; y += 30) {
      var a = point([-180, y]), b = point([180, y]);
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    }
    ctx.fillStyle = palette.land; ctx.strokeStyle = palette.coast; ctx.lineWidth = 1;
    land.forEach(function (outline) {
      ctx.beginPath();
      outline.forEach(function (pair, i) { var p = point(pair); if (i) { ctx.lineTo(p[0], p[1]); } else { ctx.moveTo(p[0], p[1]); } });
      ctx.closePath(); ctx.fill(); ctx.stroke();
    });
  }
  var background = document.createElement('canvas');
  background.width = 1000; background.height = 440;
  function buildBackground() {
    baseMap();
    var bg = background.getContext('2d');
    bg.clearRect(0, 0, 1000, 440);
    bg.drawImage(canvas, 0, 0);
  }
  readPalette(); buildBackground();
  window.addEventListener('themechange', function () {
    readPalette(); buildBackground(); drawChart(lastHistory);
  }, false);
  function bezier(a, b, c, t) {
    return [(1-t)*(1-t)*a[0]+2*(1-t)*t*b[0]+t*t*c[0], (1-t)*(1-t)*a[1]+2*(1-t)*t*b[1]+t*t*c[1]];
  }
  function draw(time) {
    ctx.clearRect(0, 0, 1000, 440); ctx.drawImage(background, 0, 0);
    var sourcePt = point(origin), active = current && current.available && Date.now() - lastSuccess < 15000;
    ctx.font = '15px "PingFang SC", "Microsoft YaHei", sans-serif';
    ctx.fillStyle = palette.accent2; ctx.beginPath(); ctx.arc(sourcePt[0], sourcePt[1], 5, 0, Math.PI*2); ctx.fill();
    ctx.fillText('家庭网络（示意）', sourcePt[0] + 12, sourcePt[1] + 23);
    if (!active) {
      ctx.fillStyle = palette.text2; ctx.fillText('等待实时连接数据', 36, 425); return;
    }
    current.countries.forEach(function (region, index) {
      var dest = point([region.lon, region.lat]);
      var distance = Math.abs(dest[0] - sourcePt[0]);
      var control = [(dest[0] + sourcePt[0])/2, Math.max(8, Math.min(dest[1],sourcePt[1]) - 35 - distance * 0.18)];
      ctx.strokeStyle = region.bytes_per_sec > 0 ? palette.accent : palette.inactive;
      ctx.lineWidth = Math.min(3, 1 + region.count/8);
      ctx.beginPath(); ctx.moveTo(sourcePt[0],sourcePt[1]); ctx.quadraticCurveTo(control[0],control[1],dest[0],dest[1]); ctx.stroke();
      if (region.bytes_per_sec > 0 && !reduced.matches) {
        for (var n = 0; n < 3; n++) {
          var t = ((time / 3200 + index * 0.13 + n/3) % 1);
          var dot = bezier(sourcePt,control,dest,t);
          ctx.fillStyle = palette.dot; ctx.shadowColor = palette.accent; ctx.shadowBlur = 9;
          ctx.beginPath(); ctx.arc(dot[0],dot[1],2.7,0,Math.PI*2); ctx.fill();
        }
      }
      ctx.shadowBlur = 0; ctx.fillStyle = palette.accent;
      ctx.beginPath(); ctx.arc(dest[0],dest[1],4 + Math.min(4,region.count/3),0,Math.PI*2); ctx.fill();
      ctx.strokeStyle = palette.accent; ctx.globalAlpha = 0.35;
      ctx.beginPath(); ctx.arc(dest[0],dest[1],12,0,Math.PI*2); ctx.stroke(); ctx.globalAlpha = 1;
      if (index < 6 && region.code !== 'CN') { ctx.fillStyle = palette.text; ctx.fillText(region.name, dest[0]+10,dest[1]-10); }
    });
  }
  function drawChart(history) {
    plot.clearRect(0,0,320,90);
    var max = 1;
    history.forEach(function (h) { max = Math.max(max,h.down || 0,h.up || 0); });
    plot.strokeStyle = palette.line; plot.beginPath(); plot.moveTo(0,87); plot.lineTo(320,87); plot.stroke();
    ['down','up'].forEach(function (key,index) {
      plot.strokeStyle = index ? palette.accent2 : palette.accent; plot.lineWidth = 2; plot.beginPath();
      var connected = false;
      history.forEach(function (h,i) {
        if (h[key] === null) { connected = false; return; }
        var x = i/59*320, y = 86-h[key]/max*65;
        if (connected) { plot.lineTo(x,y); } else { plot.moveTo(x,y); connected = true; }
      }); plot.stroke();
    });
    return max === 1 ? 0 : max;
  }
  function unavailable(message) {
    current = null; latest = null;
    text('proxy-state',message); text('proxy-down','—'); text('proxy-up','—'); text('proxy-count','—');
    text('proxy-regions','暂时没有可用的连接分布'); text('proxy-totals','等待恢复采样');
    text('proxy-freshness','此来源未返回最新数据，恢复后重新采样。');
    if (source === 'router') { text('device-rows',''); text('router-quality','设备排行暂不可用'); }
    drawChart([]); draw(0);
  }
  function deviceRows(data) {
    var body = document.getElementById('device-rows');
    var focused = document.activeElement && document.activeElement.getAttribute('data-device');
    var scroll = document.querySelector('.device-scroll'), position = scroll.scrollTop;
    while (body.firstChild) { body.removeChild(body.firstChild); }
    data.devices.forEach(function (device) {
      var row = document.createElement('tr');
      var name = document.createElement('td'), rates = document.createElement('td'), count = document.createElement('td');
      var button = document.createElement('button');
      var label = document.createElement('span'), address = document.createElement('span');
      label.className = 'dev-name';
      label.textContent = device.name === '局域网设备' ? device.ip : device.name;
      address.className = 'dev-ip'; address.textContent = device.ip;
      button.appendChild(label); button.appendChild(address);
      button.setAttribute('data-device',device.ip);
      button.setAttribute('aria-pressed',selectedDevice === device.ip ? 'true' : 'false');
      button.onclick = function () { selectedDevice = device.ip; if (latest) { render(latest); } };
      name.appendChild(button);
      rates.textContent = rate(device.receive_rate) + ' / ' + rate(device.send_rate);
      count.textContent = device.connections;
      row.appendChild(name); row.appendChild(rates); row.appendChild(count); body.appendChild(row);
      if (focused === device.ip) { button.focus(); }
    });
    scroll.scrollTop = position;
    text('router-quality','可归属设备 ' + data.devices.length + ' 台 · 速率有效记录 ' + data.sampled_connections + '/' + (data.connections-data.unassigned-data.parse_errors) + ' · 未归属 ' + data.unassigned + '（IPv6 ' + data.ipv6 + '）' + (data.parse_errors ? ' · 解析跳过 ' + data.parse_errors : '') + (data.devices.length ? '' : ' · 当前无可归属设备'));
  }
  function render(data) {
    if (!data.available) { unavailable(data.message || '采集来源暂不可达'); return; }
    if (Date.now()/1000-data.updated > 15) { unavailable('采集数据已过期'); return; }
    latest = data; lastSuccess = Date.now();
    var countries = data.countries, unknown = data.unknown;
    var router = source === 'router';
    if (router) {
      var chosen = null;
      data.devices.forEach(function (device) { if (device.ip === selectedDevice) { chosen = device; } });
      if (selectedDevice) { countries = chosen ? chosen.countries : []; unknown = chosen ? chosen.unknown : 0; }
      text('map-filter',selectedDevice ? '地图：' + (chosen ? chosen.name + ' · ' : '') + selectedDevice + (chosen ? '' : ' · 无当前记录') : '地图：全部可归属设备的公网目标');
      var ifaceName = data.interface || routerIface;
      var iface = (data.interfaces && data.interfaces[ifaceName]) || {};
      text('proxy-state','旁路由在线 · ' + ifaceName + ' · 每 5 秒采样');
      text('proxy-down',rate(iface.rx_rate)); text('proxy-up',rate(iface.tx_rate));
      lastHistory = data.history;
      var peak = drawChart(data.history);
      text('proxy-totals','网口累计 RX ' + bytes(iface.rx) + ' / TX ' + bytes(iface.tx) + ' · 区间峰值 ' + bytes(peak) + '/s');
      text('proxy-freshness','更新于 ' + new Date(data.updated*1000).toLocaleTimeString() + ' · ' + ((data.software_offload || data.hardware_offload) ? '流量卸载已配置，连接计数可能不完整。' : '短连接及采样间隙流量可能遗漏。') + (data.geo_available ? '' : ' 离线定位库不可用。'));
      deviceRows(data);
    } else {
      text('map-filter','地图：' + proxyName + ' 所见目标');
      text('proxy-state',proxyName + ' 核心在线 · ' + proxyHostLabel);
      text('proxy-down',rate(data.download_rate)); text('proxy-up',rate(data.upload_rate));
      lastHistory = data.history;
      var peak2 = drawChart(data.history);
      text('proxy-totals','核心累计 ↓ ' + bytes(data.download_total) + ' / ↑ ' + bytes(data.upload_total) + ' · 区间峰值 ' + bytes(peak2) + '/s');
      text('proxy-freshness','更新于 ' + new Date(data.updated*1000).toLocaleTimeString() + ' · 直连 ' + data.direct + ' 个 · 核心在线不等于外网可达。' + (data.geo_available ? '' : ' 离线定位库不可用。'));
    }
    current = {available: true, countries: countries.slice().sort(function (a,b) { return b.count-a.count; })};
    text('proxy-count',data.connections);
    var regions = current.countries.map(function (r) { return r.name + ' ' + r.count; });
    if (unknown) { regions.push('未定位 ' + unknown); }
    text('proxy-regions',regions.length ? regions.join('  ·  ') : '当前没有可定位的公网目标');
    draw(performance.now());
  }
  function poll() {
    if (pending || document.hidden) { return; }
    pending = true;
    var generation = requestGeneration;
    var xhr = new XMLHttpRequest(); xhr.open('GET','/api/' + source,true); xhr.timeout = 8000;
    xhr.onload = function () {
      if (generation !== requestGeneration) { return; }
      pending = false;
      if (xhr.status !== 200) { unavailable('监控连接中断'); return; }
      try { render(JSON.parse(xhr.responseText)); } catch (err) { unavailable('数据读取失败'); }
    };
    xhr.onerror = xhr.ontimeout = function () {
      if (generation !== requestGeneration) { return; }
      pending = false; unavailable('监控连接中断');
    };
    xhr.send();
  }
  function selectSource(value) {
    source = value; requestGeneration++; pending = false;
    var router = source === 'router';
    document.getElementById('source-router').setAttribute('aria-pressed',router ? 'true' : 'false');
    document.getElementById('source-proxy').setAttribute('aria-pressed',router ? 'false' : 'true');
    document.getElementById('device-panel').hidden = !router;
    document.body.classList.toggle('proxy-source', !router);
    text('network-scope',router ? '旁路由可见流量 · ' + routerLabel : '独立代理视图 · ' + proxyHostLabel);
    text('rx-label',router ? '网口接收 RX' : '下载'); text('tx-label',router ? '网口发送 TX' : '上传');
    text('count-label',router ? '跟踪记录' : '当前连接');
    text('map-filter',router ? '地图：全部可归属设备的公网目标' : '地图：' + proxyName + ' 所见目标');
    text('proxy-note',router ? '仅覆盖经过旁路由的流量，含本机及采集开销；RX/TX 不是宽带上下行。排行为连接采样值，不能与网口相加。地图为地区示意，起点非实际位置。' : '仅统计经过代理核心的流量，包含直连；与旁路由数据独立。地图为地区示意，不代表真实路由或实际家庭位置。');
    document.getElementById('traffic-chart').setAttribute('aria-label',router ? '最近约五分钟网口收发速率趋势' : '最近约三分钟代理上下行速率趋势');
    unavailable('正在连接' + (router ? '旁路由' : proxyName));
    poll();
  }

  document.getElementById('source-router').hidden = !hasRouter;
  document.getElementById('source-proxy').hidden = !hasProxy;
  document.getElementById('source-proxy').textContent = proxyName + ' 代理';
  document.getElementById('source-router').onclick = function () { selectSource('router'); };
  document.getElementById('source-proxy').onclick = function () { selectSource('proxy'); };
  document.getElementById('all-devices').onclick = function () { selectedDevice = null; if (latest) { render(latest); } };
  function animate(time) {
    if (!document.hidden && time-lastFrame > 50) {
      lastFrame = time;
      if (current && Date.now()-lastSuccess >= 15000) { unavailable('采集数据已过期'); }
      if (!reduced.matches) { draw(time); }
    }
    requestAnimationFrame(animate);
  }
  function setFocus(focused) {
    document.body.classList.toggle('network-focus', focused);
    var button = document.getElementById('focus-network');
    button.textContent = focused ? '显示全部面板' : '专注地图';
    button.setAttribute('aria-pressed', focused ? 'true' : 'false');
  }
  document.getElementById('focus-network').onclick = function () {
    var focused = !document.body.classList.contains('network-focus');
    setFocus(focused);
    try { localStorage.setItem('network-focus', focused ? 'yes' : 'no'); } catch (err) {}
    if (focused) { window.scrollTo(0,0); }
  };
  try { setFocus(localStorage.getItem('network-focus') === 'yes'); } catch (err) { setFocus(false); }
  document.addEventListener('visibilitychange',function () { if (!document.hidden) { poll(); } });
  selectSource(source); setInterval(poll,3000); requestAnimationFrame(animate);
}());
