/* Radio player: the <audio> element is created once and never rebuilt, so the
   dashboard's 3-30s data polling can never interrupt playback. ES5 for iOS 12. */
(function () {
  'use strict';
  var cfg = window.DASHBOARD_CONFIG || {};
  var features = cfg.features || {};
  if (features.radio === false) { return; }

  var audio = document.getElementById('radio-audio');
  var playButton = document.getElementById('radio-play');
  var stationLabel = document.getElementById('radio-station');
  var stateLabel = document.getElementById('radio-state');
  var sheet = document.getElementById('radio-sheet');
  var groups = document.getElementById('radio-groups');
  var listToggle = document.getElementById('radio-list-toggle');
  var closeButton = document.getElementById('radio-close');
  var searchBox = document.getElementById('music-search-box');
  var searchInput = document.getElementById('music-q');
  var searchState = document.getElementById('music-state');
  var searchResults = document.getElementById('music-results');
  var setTab = window.initLibraryPanel(playLibrarySong, store);

  if (features.music_search === false) {
    if (searchBox) { searchBox.hidden = true; }
    if (searchResults) { searchResults.hidden = true; }
  }

  var stations = [];
  var current = null;
  var attempts = 0;
  var retryTimer = null;
  var fadeTimer = null;
  var titleTimer = null;
  var wanted = false;
  var targetVolume = 0.4;
  var MAX_VOLUME = 0.8;
  var RETRY_STEPS = [1000, 2000, 4000, 8000, 15000, 30000, 30000, 30000];

  function store(key, value) {
    try { window.localStorage.setItem(key, value); } catch (err) {}
  }
  function load(key, fallback) {
    try {
      var value = window.localStorage.getItem(key);
      return value === null ? fallback : value;
    } catch (err) { return fallback; }
  }
  function clearTimer(timer) {
    if (timer) { clearTimeout(timer); }
    return null;
  }

  function setState(text) { stateLabel.textContent = text; }

  function setPlaying(playing) {
    audio.setAttribute('aria-pressed', playing ? 'true' : 'false');
    playButton.textContent = playing ? '❚❚' : '▶';
    playButton.setAttribute('aria-pressed', playing ? 'true' : 'false');
    playButton.setAttribute('aria-label', playing ? '暂停广播' : '播放广播');
    document.body.classList[playing ? 'add' : 'remove']('radio-playing');
  }

  function fadeTo(level) {
    if (fadeTimer) { clearInterval(fadeTimer); fadeTimer = null; }
    var start = audio.volume || 0;
    var steps = 10;
    var index = 0;
    fadeTimer = setInterval(function () {
      index += 1;
      audio.volume = Math.min(1, Math.max(0, start + (level - start) * index / steps));
      if (index >= steps) {
        clearInterval(fadeTimer);
        fadeTimer = null;
        audio.volume = level;
      }
    }, 80);
  }

  function pick(id) {
    var found = null;
    stations.forEach(function (item) { if (item.id === id) { found = item; } });
    return found;
  }

  function showStation(station) {
    current = station;
    if (station) { station.kind = 'station'; }
    stationLabel.textContent = station ? station.name : '未选择电台';
    if (!station) { setState('点一下开始播放'); return; }
    var health = station.health || {};
    if (health.status === 'fail') { setState('上次探测不可达，仍可尝试'); }
    else if (station.codec === 'hls') { setState('HLS · 点击播放'); }
    else { setState('点击播放'); }
  }

  function remember() {
    if (current && current.kind === 'station') { store('radio.station', current.id); }
    if (current && current.kind === 'track') {
      store('radio.track', JSON.stringify({id: current.id, name: current.name,
                                           artist: current.artist || '',
                                           source: current.source || 'online'}));
    } else { store('radio.track', ''); }
    store('radio.volume', String(targetVolume));
    store('radio.wanted', wanted ? '1' : '0');
  }

  function stopTimers() {
    retryTimer = clearTimer(retryTimer);
    if (titleTimer) { clearInterval(titleTimer); titleTimer = null; }
  }

  function pollTitle() {
    if (!current || current.kind !== 'station') { return; }
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/radio/now?id=' + encodeURIComponent(current.id), true);
    xhr.timeout = 8000;
    xhr.onload = function () {
      if (xhr.status !== 200 || !current) { return; }
      try {
        var data = JSON.parse(xhr.responseText);
        if (data && data.title) {
          stationLabel.textContent = current.name + ' · ' + data.title;
        } else {
          stationLabel.textContent = current.name;
        }
      } catch (err) {}
    };
    xhr.send();
  }

  function scheduleRetry() {
    if (!wanted || !current) { return; }
    if (attempts >= RETRY_STEPS.length) {
      setState('连接失败 · 请手动重试');
      wanted = false;
      remember();
      setPlaying(false);
      return;
    }
    var delay = RETRY_STEPS[attempts];
    attempts += 1;
    setState('重连中 ' + attempts + '/' + RETRY_STEPS.length + ' · ' + Math.round(delay / 1000) + ' 秒后');
    retryTimer = clearTimer(retryTimer);
    retryTimer = setTimeout(function () {
      retryTimer = null;
      if (wanted) { start(); }
    }, delay);
  }

  function startTrack(track) {
    if (track.source === 'library') {
      current = track;
      current.url = '/api/library/audio?id=' + encodeURIComponent(track.id);
      start();
      return;
    }
    current = track;
    setState('取播放地址…');
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/music/url?id=' + encodeURIComponent(track.id), true);
    xhr.timeout = 9000;
    xhr.onload = function () {
      var resolved = null;
      try { resolved = JSON.parse(xhr.responseText); } catch (err) {}
      if (!resolved || !resolved.available || !resolved.url) {
        setPlaying(false);
        wanted = false;
        remember();
        setState((resolved && resolved.message) || '取不到播放地址');
        return;
      }
      current.url = resolved.url;
      start();
    };
    xhr.onerror = function () { setState('取播放地址失败'); setPlaying(false); };
    xhr.send();
  }

  function start() {
    if (!current) { return; }
    retryTimer = clearTimer(retryTimer);
    setState('连接中…');
    audio.volume = 0;
    audio.src = current.url;
    audio.load();
    var promise = audio.play();
    if (promise && promise.catch) {
      promise.catch(function () {
        setPlaying(false);
        wanted = false;
        remember();
        setState('需要点击才能播放');
      });
    }
  }

  function play() {
    if (!current) { openSheet(); return; }
    wanted = true;
    attempts = 0;
    remember();
    if (current.kind === 'track' && !current.url) {
      startTrack(current);
    } else {
      start();
    }
    if (titleTimer) { clearInterval(titleTimer); }
    titleTimer = setInterval(pollTitle, 20000);
  }

  function pause() {
    wanted = false;
    stopTimers();
    remember();
    audio.pause();
    setPlaying(false);
    setState('已暂停');
    if (current) { stationLabel.textContent = labelOf(current); }
  }

  function labelOf(item) {
    if (!item) { return '未选择'; }
    return item.kind === 'track' && item.artist ? item.name + ' · ' + item.artist : item.name;
  }

  function chooseTrack(item) {
    closeSheet();
    stopTimers();
    wanted = true;
    attempts = 0;
    setPlaying(false);
    stationLabel.textContent = labelOf({kind: 'track', name: item.name, artist: item.artist});
    current = {kind: 'track', id: item.id, name: item.name, artist: item.artist, url: ''};
    remember();
    startTrack(current);
    titleTimer = setInterval(pollTitle, 20000);
  }

  function choose(id) {
    var station = pick(id);
    if (!station) { return; }
    closeSheet();
    showStation(station);
    wanted = true;
    attempts = 0;
    remember();
    stopTimers();
    start();
    titleTimer = setInterval(pollTitle, 20000);
  }

  audio.addEventListener('playing', function () {
    attempts = 0;
    setPlaying(true);
    if (current) { stationLabel.textContent = labelOf(current); }
    setState(current && current.codec === 'hls' ? '播放中 · HLS' : '播放中');
    fadeTo(targetVolume);
    pollTitle();
  }, false);
  audio.addEventListener('waiting', function () {
    if (wanted) { setState('缓冲中…'); }
  }, false);
  audio.addEventListener('pause', function () {
    if (!wanted) { setPlaying(false); }
  }, false);
  audio.addEventListener('error', function () {
    if (!wanted) { return; }
    setPlaying(false);
    if (current && current.kind === 'track' && current.source !== 'library' && attempts === 0) {
      attempts = 1;
      setState('链接可能过期，重新取地址…');
      startTrack(current);
      return;
    }
    scheduleRetry();
  }, false);
  audio.addEventListener('stalled', function () {
    if (!wanted) { return; }
    setState('信号中断');
  }, false);

  playButton.onclick = function () {
    if (wanted && !audio.paused) { pause(); } else { play(); }
  };

  var searchTimer = null;
  var searchSeq = 0;

  function setSearchState(text) { searchState.textContent = text; }

  function renderResults(items) {
    while (searchResults.firstChild) { searchResults.removeChild(searchResults.firstChild); }
    if (!items.length) { searchResults.hidden = true; return; }
    items.forEach(function (item) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'music-result';
      var name = document.createElement('span');
      name.textContent = item.name;
      var meta = document.createElement('small');
      meta.textContent = item.artist || '';
      button.appendChild(name);
      button.appendChild(meta);
      button.onclick = function () { chooseTrack(item); };
      searchResults.appendChild(button);
    });
    searchResults.hidden = false;
  }

  function runSearch(query) {
    searchSeq += 1;
    var seq = searchSeq;
    setSearchState('搜索中…');
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/music/search?q=' + encodeURIComponent(query), true);
    xhr.timeout = 12000;
    xhr.onload = function () {
      if (seq !== searchSeq) { return; }
      var data = null;
      try { data = JSON.parse(xhr.responseText); } catch (err) {}
      if (!data) { setSearchState('搜索失败'); return; }
      if (!data.available) { setSearchState(data.message || '第三方接口不可用'); renderResults([]); return; }
      renderResults(data.items || []);
      var items = data.items || [];
      var source = data.source || (items[0] && items[0].source) || '';
      setSearchState(items.length
        ? (source === 'qq' ? 'QQ 音乐 · 第三方' : '网易云 · 第三方')
        : '没有结果');
    };
    xhr.onerror = function () { if (seq === searchSeq) { setSearchState('网络错误'); } };
    xhr.ontimeout = function () { if (seq === searchSeq) { setSearchState('搜索超时'); } };
    xhr.send();
  }

  if (searchInput && features.music_search !== false) {
    searchInput.oninput = function () {
      var query = searchInput.value.trim();
      if (searchTimer) { clearTimeout(searchTimer); searchTimer = null; }
      if (query.length < 2) {
        searchSeq += 1;
        renderResults([]);
        setSearchState(query ? '至少 2 个字符' : '');
        return;
      }
      searchTimer = setTimeout(function () { searchTimer = null; runSearch(query); }, 600);
    };
  }

  function playLibrarySong(song) {
    closeSheet();
    stopTimers();
    wanted = true;
    attempts = 0;
    setPlaying(false);
    current = {kind: 'track', source: 'library', id: song.id, name: song.title,
               artist: song.artist || '', url: ''};
    stationLabel.textContent = labelOf(current);
    remember();
    startTrack(current);
    titleTimer = setInterval(pollTitle, 20000);
  }

  function openSheet() {
    sheet.hidden = false;
    setTab(features.library ? load('radio.tab', 'radio') : 'radio');
    listToggle.setAttribute('aria-expanded', 'true');
    var first = groups.querySelector('button');
    if (first) { first.focus(); }
  }
  function closeSheet() {
    sheet.hidden = true;
    listToggle.setAttribute('aria-expanded', 'false');
  }
  listToggle.onclick = function () { if (sheet.hidden) { openSheet(); } else { closeSheet(); } };
  closeButton.onclick = closeSheet;
  sheet.onclick = function (event) { if (event.target === sheet) { closeSheet(); } };

  function renderStations() {
    while (groups.firstChild) { groups.removeChild(groups.firstChild); }
    var order = [];
    stations.forEach(function (item) {
      if (order.indexOf(item.group) === -1) { order.push(item.group); }
    });
    order.forEach(function (group) {
      var heading = document.createElement('h3');
      heading.textContent = group;
      groups.appendChild(heading);
      var list = document.createElement('div');
      list.className = 'radio-options';
      stations.forEach(function (item) {
        if (item.group !== group) { return; }
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'radio-option';
        var name = document.createElement('span');
        name.textContent = item.name;
        var dot = document.createElement('i');
        var status = (item.health && item.health.status) || 'unknown';
        dot.className = 'radio-dot ' + status;
        dot.title = status === 'ok' ? '最近探测可用' : (status === 'fail' ? '最近探测不可达' : '尚未探测');
        button.appendChild(name);
        button.appendChild(dot);
        if (current && current.id === item.id) { button.setAttribute('aria-pressed', 'true'); }
        button.onclick = function () { choose(item.id); };
        list.appendChild(button);
      });
      groups.appendChild(list);
    });
    if (!stations.length) {
      var empty = document.createElement('p');
      empty.className = 'hint';
      empty.textContent = '暂时没有可用电台，检查 stations.json。';
      groups.appendChild(empty);
    }
  }

  function loadStations() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/radio', true);
    xhr.timeout = 10000;
    xhr.onload = function () {
      if (xhr.status !== 200) { return; }
      try {
        var data = JSON.parse(xhr.responseText);
        stations = data.stations || [];
        if (current) {
          var updated = pick(current.id);
          if (updated) { current = updated; }
        }
        renderStations();
      } catch (err) {}
    };
    xhr.send();
  }

  var savedVolume = parseFloat(load('radio.volume', '0.4'));
  if (!isNaN(savedVolume) && savedVolume > 0) {
    targetVolume = Math.min(MAX_VOLUME, savedVolume);
  }
  audio.volume = targetVolume;

  var savedStation = load('radio.station', '');
  var wasWanted = load('radio.wanted', '0') === '1';

  loadStations();
  setInterval(loadStations, 600000);

  var restore = setInterval(function () {
    if (!stations.length) { return; }
    clearInterval(restore);
    var savedTrack = null;
    try { savedTrack = JSON.parse(load('radio.track', '') || 'null'); } catch (err) {}
    if (savedTrack && savedTrack.id) {
      if (savedTrack.source === 'library' && !features.library) { savedTrack = null; }
    }
    if (savedTrack && savedTrack.id) {
      current = {kind: 'track', id: savedTrack.id, name: savedTrack.name,
                 artist: savedTrack.artist, source: savedTrack.source || 'online',
                 url: savedTrack.source === 'library'
                   ? '/api/library/audio?id=' + encodeURIComponent(savedTrack.id) : ''};
      stationLabel.textContent = savedTrack.name + (savedTrack.artist ? ' · ' + savedTrack.artist : '');
      setPlaying(false);
      setState(wasWanted ? '点击继续播放' : '已暂停');
      return;
    }
    var station = pick(savedStation);
    if (!station) {
      if (stations.length) { showStation(stations[0]); }
      setPlaying(false);
      return;
    }
    showStation(station);
    if (wasWanted) {
      setState('点击继续播放');
    }
  }, 400);
}());
