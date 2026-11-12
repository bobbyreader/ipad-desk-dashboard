/* Library panel for iOS 12: ES5 and same-origin XHR. */
window.initLibraryPanel = function (playLibrarySong, store, addToPlaylist, onOpenPlaylist) {
  'use strict';
  var cfg = window.DASHBOARD_CONFIG || {};
  var features = cfg.features || {};
  var hasLibrary = !!features.library;
  var hasPlaylist = hasLibrary || features.music_search !== false;
  var tabsBar = document.getElementById('radio-tabs-bar');
  var tabRadio = document.getElementById('tab-radio');
  var tabLibrary = document.getElementById('tab-library');
  var tabPlaylist = document.getElementById('tab-playlist');
  var paneRadio = document.getElementById('pane-radio');
  var paneLibrary = document.getElementById('pane-library');
  var panePlaylist = document.getElementById('pane-playlist');
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
  if (tabsBar) { tabsBar.hidden = !hasPlaylist; }
  if (tabLibrary) { tabLibrary.hidden = !hasLibrary; }
  if (!hasLibrary && paneLibrary) { paneLibrary.hidden = true; }
  if (tabPlaylist) { tabPlaylist.hidden = !hasPlaylist; }
  if (!hasPlaylist && panePlaylist) { panePlaylist.hidden = true; }

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
    var playableList = songs.filter(function (s) { return !!s.playable; });
    songs.forEach(function (song) {
      var meta = song.playable
        ? (song.duration ? Math.floor(song.duration / 60) + ':' + ('0' + (song.duration % 60)).slice(-2) : '')
        : '格式不支持';
      var wrap = document.createElement('div');
      wrap.className = 'track-item';
      var row = makeRow(song.title, meta, !song.playable);
      if (song.playable) {
        row.onclick = function () { playLibrarySong(song, playableList); };
      }
      wrap.appendChild(row);
      if (song.playable && addToPlaylist) {
        var addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.className = 'track-add';
        addBtn.textContent = '+';
        addBtn.setAttribute('aria-label', '加入歌单');
        addBtn.onclick = function (e) {
          e.stopPropagation();
          addToPlaylist({
            id: song.id,
            name: song.title,
            artist: song.artist || '',
            source: 'library'
          });
          addBtn.textContent = '✓';
          setTimeout(function () { addBtn.textContent = '+'; }, 900);
        };
        wrap.appendChild(addBtn);
      }
      libList.appendChild(wrap);
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
    if (name === 'library' && !hasLibrary) { name = 'radio'; }
    if (name === 'playlist' && !hasPlaylist) { name = 'radio'; }
    var isLib = name === 'library';
    var isPl = name === 'playlist';
    var isRad = !isLib && !isPl;
    if (tabRadio) { tabRadio.setAttribute('aria-pressed', isRad ? 'true' : 'false'); }
    if (tabLibrary) { tabLibrary.setAttribute('aria-pressed', isLib ? 'true' : 'false'); }
    if (tabPlaylist) { tabPlaylist.setAttribute('aria-pressed', isPl ? 'true' : 'false'); }
    if (paneRadio) { paneRadio.hidden = !isRad; }
    if (paneLibrary) { paneLibrary.hidden = !isLib; }
    if (panePlaylist) { panePlaylist.hidden = !isPl; }
    store('radio.tab', name);
    if (isLib && !libAlbums) { loadAlbums(); }
    if (isPl && onOpenPlaylist) { onOpenPlaylist(); }
  }

  if (tabRadio) { tabRadio.onclick = function () { setTab('radio'); }; }
  if (tabLibrary) { tabLibrary.onclick = function () { setTab('library'); }; }
  if (tabPlaylist) { tabPlaylist.onclick = function () { setTab('playlist'); }; }
  libBack.onclick = function () { renderAlbums(); };
  libQ.oninput = function () {
    var query = libQ.value.trim();
    if (libTimer) { clearTimeout(libTimer); libTimer = null; }
    if (!query) { renderAlbums(); return; }
    libTimer = setTimeout(function () { libTimer = null; searchLibrary(query); }, 500);
  };

  return setTab;
};
