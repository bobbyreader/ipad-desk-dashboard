/* Readhub hot topics: one ticker, same scroll behavior as AIHOT. */
(function () {
  'use strict';
  var cfg = window.DASHBOARD_CONFIG || {};
  var features = cfg.features || {};
  if (features.readhub === false) { return; }

  var list = document.getElementById('readhub-list');
  var ticker = new window.Ticker(list, { visible: 3, autoFit: true });
  var data = null;

  function build() {
    var topics = (data && data.topics) || [];
    ticker.setItems(topics, {
      title: function (row) { return row.title; },
      url: function (row) { return /^https:\/\/readhub\.cn\/topic\//.test(row.url || '') ? row.url : ''; },
      meta: function (row) {
        var parts = [row.source || 'Readhub'];
        if (row.sites) { parts.push(row.sites + ' 家媒体'); }
        if (row.published) { parts.push(window.tickerClock(row.published)); }
        return parts.join(' · ');
      }
    });
    ticker.start();
    status();
  }

  function status() {
    if (!data || !data.available) {
      window.tickerStatus('readhub-status', (data && data.message) || 'Readhub 暂时不可达');
      return;
    }
    var note = (data.stale ? ' · 内容可能已过期' : '') + (data.error ? ' · ' + data.error : '');
    window.tickerStatus('readhub-status', '更新于 ' + new Date(data.updated * 1000).toLocaleTimeString() +
      ' · ' + ((data.topics || []).length) + ' 条话题' + note);
  }

  function load() {
    if (document.hidden) { return; }
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/readhub', true);
    xhr.timeout = 15000;
    xhr.onload = function () {
      if (xhr.status !== 200) { window.tickerStatus('readhub-status', 'Readhub 面板连接中断'); return; }
      try { data = JSON.parse(xhr.responseText); } catch (err) {
        window.tickerStatus('readhub-status', 'Readhub 数据读取失败');
        return;
      }
      if (data.available) { build(); } else { ticker.clear(); status(); }
    };
    xhr.onerror = xhr.ontimeout = function () { window.tickerStatus('readhub-status', 'Readhub 面板连接中断'); };
    xhr.send();
  }

  document.addEventListener('visibilitychange', function () { if (!document.hidden) { load(); } });
  load();
  setInterval(load, 600000);
}());
