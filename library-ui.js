/* Library panel for iOS 12: ES5 and same-origin XHR. */
window.initLibraryPanel = function (playLibrarySong, store) {
  'use strict';
  var cfg = window.DASHBOARD_CONFIG || {};
  var features = cfg.features || {};
  var enabled = !!features.library;
  var tabsBar = document.getElementById('radio-tabs-bar');
  var tabRadio = document.getElementById('tab-radio');
  var tabLibrary = document.getElementById('tab-library');
  var paneRadio = document.getElementById('pane-radio');
  var paneLibrary = document.getElementById('pane-library');
  var libQ = document.getElementById('lib-q');
  var libState = document.getElementById('lib-state');
  var libList = document.getElementById('lib-list');
  var libHead = document.getElementById('lib-head');
  var libAlbum = document.getElementById('lib-album');
  var libBack = document.getElementById('lib-back');
  var libHint = document.getElementById('lib-hint');
  var libAlbums = null;
  var libTimer = null;

  if (libHint && cfg.library && cfg.library.hint) {
    libHint.textContent = cfg.library.hint;
  }
  if (!enabled) {
    if (tabsBar) { tabsBar.hidden = true; }
    if (tabLibrary) { tabLibrary.hidden = true; }
    if (paneLibrary) { paneLibrary.hidden = true; }
    if (paneRadio) { paneRadio.hidden = false; }
    return function () {};
  }

  function makeRow(main, meta, disabled) {
    var row = document.createElement('button');
    row.type = 'button';
    row.className = 'lib-row';
    var title = document.createElement('span');
    title.textContent = main;
    var extra = document.createElement('small');
    extra.textContent = meta || '';
    row.appendChild(title);
    row.appendChild(extra);
    if (disabled) { row.disabled = true; }
    return row;
  }

  function clearNode(node) {
    while (node.firstChild) { node.removeChild(node.firstChild); }
  }

  function renderAlbums() {
    clearNode(libList);
    libHead.hidden = true;
    if (!libAlbums) { return; }
    libAlbums.forEach(function (album) {
      var row = makeRow(album.name, album.artist + ' · ' + album.songCount + ' 首');
      var cover = document.createElement('span');
      cover.className = 'lib-cover';
      cover.textContent = '♪';
      cover.setAttribute('aria-hidden', 'true');
      if (album.coverId) {
        var img = document.createElement('img');
        img.alt = '';
        img.width = 44;
        img.height = 44;
        img.src = '/api/library/cover?id=' + encodeURIComponent(album.coverId);
        img.onerror = function () { if (img.parentNode) { img.parentNode.removeChild(img); } };
        cover.appendChild(img);
      }
      row.insertBefore(cover, row.firstChild);
      row.className += ' lib-album-row';
      row.onclick = function () { openAlbum(album.id, album.name); };
      libList.appendChild(row);
    });
    libState.textContent = libAlbums.length + ' 张专辑';
  }

  function loadAlbums() {
    libState.textContent = '读取音乐库…';
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/library/albums', true);
    xhr.timeout = 15000;
    xhr.onload = function () {
      var data = null;
      try { data = JSON.parse(xhr.responseText); } catch (err) {}
      if (!data || !data.available) {
        libState.textContent = (data && data.message) || '音乐库不可用';
        return;
      }
      libAlbums = data.albums || [];
      renderAlbums();
    };
    xhr.onerror = function () { libState.textContent = '读取失败'; };
    xhr.send();
  }

  function openAlbum(id, name) {
    clearNode(libList);
    libHead.hidden = false;
    libAlbum.textContent = name;
    libState.textContent = '读取曲目…';
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/library/album?id=' + encodeURIComponent(id), true);
    xhr.timeout = 15000;
    xhr.onload = function () {
      var data = null;
      try { data = JSON.parse(xhr.responseText); } catch (err) {}
      if (!data || !data.available) {
        libState.textContent = (data && data.message) || '读取专辑失败';
        return;
      }
      renderSongs(data.songs || []);
      libState.textContent = (data.songs || []).length + ' 首';
    };
    xhr.onerror = function () { libState.textContent = '读取失败'; };
    xhr.send();
  }

  function renderSongs(songs) {
    clearNode(libList);
    songs.forEach(function (song) {
      var meta = song.playable
        ? (song.duration ? Math.floor(song.duration / 60) + ':' + ('0' + (song.duration % 60)).slice(-2) : '')
        : '格式不支持';
      var row = makeRow(song.title, meta, !song.playable);
      if (song.playable) {
        row.onclick = function () { playLibrarySong(song); };
      }
      libList.appendChild(row);
    });
    if (!songs.length) { libState.textContent = '这张专辑没有可播放的曲目'; }
  }

  function searchLibrary(query) {
    libState.textContent = '搜索中…';
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/library/search?q=' + encodeURIComponent(query), true);
    xhr.timeout = 15000;
    xhr.onload = function () {
      var data = null;
      try { data = JSON.parse(xhr.responseText); } catch (err) {}
      if (!data || !data.available) {
        libState.textContent = (data && data.message) || '搜索失败';
        return;
      }
      libHead.hidden = true;
      renderSongs(data.songs || []);
      libState.textContent = (data.songs || []).length + ' 个结果';
    };
    xhr.onerror = function () { libState.textContent = '搜索失败'; };
    xhr.send();
  }

  function setTab(name) {
    var library = name === 'library';
    tabRadio.setAttribute('aria-pressed', library ? 'false' : 'true');
    tabLibrary.setAttribute('aria-pressed', library ? 'true' : 'false');
    paneRadio.hidden = library;
    paneLibrary.hidden = !library;
    store('radio.tab', library ? 'library' : 'radio');
    if (library && !libAlbums) { loadAlbums(); }
  }

  tabRadio.onclick = function () { setTab('radio'); };
  tabLibrary.onclick = function () { setTab('library'); };
  libBack.onclick = function () { renderAlbums(); };
  libQ.oninput = function () {
    var query = libQ.value.trim();
    if (libTimer) { clearTimeout(libTimer); libTimer = null; }
    if (!query) { renderAlbums(); return; }
    libTimer = setTimeout(function () { libTimer = null; searchLibrary(query); }, 500);
  };

  return setTab;
};
