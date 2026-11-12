/* AIHOT headlines: two tabs over one shared ticker. */
(function () {
  'use strict';
  var cfg = window.DASHBOARD_CONFIG || {};
  var features = cfg.features || {};
  if (features.aihot === false) { return; }

  var list = document.getElementById('news-list');
  var data = null, mode = 'hot';
  var ticker = new window.Ticker(list, { visible: 4, autoFit: true });
  function rows() {
    if (!data) { return []; }
    return data[mode === 'hot' ? 'hot' : 'selected'] || [];
  }
  function build() {
    ticker.setItems(rows(), {
      title: function (row) { return row.title; },
      url: function (row) { return /^https:\/\/aihot\.news\//.test(row.url || '') ? row.url : ''; },
      meta: function (row) {
        var prefix = mode === 'hot' && row.rank ? row.rank + '. ' : '';
        return prefix + (row.source || 'AIHOT') + (row.category ? ' · ' + row.category : '') +
          (row.published ? ' · ' + window.tickerClock(row.published) : '');
      }
    });
    ticker.start();
    if (data && data.available) { status(); }
  }
  function status() {
    if (!data || !data.available) {
      window.tickerStatus('news-status', (data && data.message) || 'AIHOT 暂时不可达');
      return;
    }
    var note = (data.stale ? ' · 内容可能已过期' : '') + (data.error ? ' · ' + data.error : '');
    window.tickerStatus('news-status', '更新于 ' + new Date(data.updated * 1000).toLocaleTimeString() +
      ' · ' + rows().length + ' 条' + note);
  }
  function setMode(value) {
    mode = value;
    document.getElementById('news-hot').setAttribute('aria-pressed', mode === 'hot' ? 'true' : 'false');
    document.getElementById('news-daily').setAttribute('aria-pressed', mode === 'hot' ? 'false' : 'true');
    build();
  }
  function render(payload) {
    data = payload;
    if (!data.available) {
      ticker.clear();
      status();
      return;
    }
    if (mode === 'hot' && !data.hot.length && data.selected.length) { setMode('daily'); return; }
    build();
  }
  function load() {
    if (document.hidden) { return; }
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/aihot', true);
    xhr.timeout = 15000;
    xhr.onload = function () {
      if (xhr.status !== 200) { window.tickerStatus('news-status', 'AIHOT 面板连接中断'); return; }
      try { render(JSON.parse(xhr.responseText)); } catch (err) { window.tickerStatus('news-status', 'AIHOT 数据读取失败'); }
    };
    xhr.onerror = xhr.ontimeout = function () { window.tickerStatus('news-status', 'AIHOT 面板连接中断'); };
    xhr.send();
  }
  document.getElementById('news-hot').onclick = function () { setMode('hot'); };
  document.getElementById('news-daily').onclick = function () { setMode('daily'); };
  document.addEventListener('visibilitychange', function () { if (!document.hidden) { load(); } });
  load();
  setInterval(load, 600000);
}());
