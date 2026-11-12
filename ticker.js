/* Shared auto-scrolling list: transform-only, seamless wrap, ES5 for iOS 12. */
(function () {
  'use strict';
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

  function Ticker(list, options) {
    this.list = list;
    this.visible = options.visible || 4;
    this.baseRowHeight = options.rowHeight || 46;
    this.rowHeight = this.baseRowHeight;
    this.stepMs = options.stepMs || 4200;
    this.autoFit = !!options.autoFit;
    this.offset = 0;
    this.count = 0;
    this.pausedUntil = 0;
    this.timer = null;
    this.resetTimer = null;
    this.items = [];
    this.mapper = null;
    var self = this;
    ['pointerdown', 'touchstart', 'mouseenter'].forEach(function (name) {
      list.addEventListener(name, function () { self.pausedUntil = Date.now() + 12000; }, false);
    });
    list.style.transition = 'transform .55s ease';
    instances.push(this);
  }

  Ticker.prototype.row = function (data, duplicate) {
    var li = document.createElement('li');
    li.className = 'news-item';
    if (duplicate) { li.setAttribute('aria-hidden', 'true'); }
    var title = document.createElement('div');
    title.className = 'news-title';
    var url = this.mapper.url(data);
    if (url) {
      var link = document.createElement('a');
      link.href = url;
      link.textContent = this.mapper.title(data);
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      if (duplicate) { link.tabIndex = -1; }
      title.appendChild(link);
    } else {
      title.textContent = this.mapper.title(data);
    }
    var meta = document.createElement('div');
    meta.className = 'news-meta';
    meta.textContent = this.mapper.meta(data);
    li.appendChild(title);
    li.appendChild(meta);
    return li;
  };

  Ticker.prototype.clear = function () {
    while (this.list.firstChild) { this.list.removeChild(this.list.firstChild); }
    this.count = 0;
    this.offset = 0;
    this.items = [];
    this.move(0, false);
  };

  Ticker.prototype.move = function (offset, animate) {
    this.list.style.transition = animate ? 'transform .55s ease' : 'none';
    this.list.style.transform = 'translateY(-' + (offset * this.rowHeight) + 'px)';
    if (!animate) {
      // Force a style flush so the next animated move starts from this position.
      void this.list.offsetHeight;
      this.list.style.transition = 'transform .55s ease';
    }
  };

  Ticker.prototype.fit = function () {
    if (!this.autoFit) { return false; }
    var wrap = this.list.parentNode;
    var height = wrap ? wrap.clientHeight : 0;
    if (!height) { return false; }
    var next = Math.max(2, Math.floor(height / this.baseRowHeight));
    var rowHeight = Math.floor(height / next);
    if (next === this.visible && rowHeight === this.rowHeight) { return false; }
    this.visible = next;
    this.rowHeight = rowHeight;
    return true;
  };

  Ticker.prototype.render = function () {
    while (this.list.firstChild) { this.list.removeChild(this.list.firstChild); }
    this.offset = 0;
    var self = this;
    if (!this.mapper) { return; }
    var add = function (data, duplicate) {
      var li = self.row(data, duplicate);
      li.style.height = self.rowHeight + 'px';
      self.list.appendChild(li);
    };
    this.items.forEach(function (data) { add(data, false); });
    if (this.items.length > this.visible) {
      this.items.forEach(function (data) { add(data, true); });
    }
    this.move(0, false);
  };

  Ticker.prototype.setItems = function (items, mapper) {
    this.items = items;
    this.mapper = mapper;
    this.count = items.length;
    var self = this;
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    if (this.resetTimer) { clearTimeout(this.resetTimer); this.resetTimer = null; }
    this.fit();
    this.render();
    this.start();
  };

  Ticker.prototype.step = function () {
    if (!this.count || this.count <= this.visible) { return; }
    if (document.hidden || reduced.matches || Date.now() < this.pausedUntil) { return; }
    if (this.resetTimer) { return; }
    var next = this.offset + 1;
    var self = this;
    if (this.resetTimer) { clearTimeout(this.resetTimer); this.resetTimer = null; }
    if (next >= this.count) {
      // The duplicate copy makes offset==count pixel-identical to offset==0.
      this.move(next, true);
      this.offset = 0;
      this.resetTimer = setTimeout(function () { self.move(0, false); self.resetTimer = null; }, 600);
    } else {
      this.offset = next;
      this.move(next, true);
    }
  };

  var instances = [];
  // Re-measure after the page layout changes (window resize, orientation, view switch).
  window.TickerRefit = function () {
    for (var i = 0; i < instances.length; i += 1) {
      if (instances[i].fit()) { instances[i].render(); }
    }
  };
  window.addEventListener('resize', window.TickerRefit, false);

  Ticker.prototype.start = function () {
    var self = this;
    if (this.timer) { clearInterval(this.timer); }
    this.timer = setInterval(function () { self.step(); }, this.stepMs);
  };

  window.Ticker = Ticker;
  window.tickerText = function (id, value) {
    var node = document.getElementById(id);
    if (node) { node.textContent = value; }
  };
  window.tickerStatus = function (id, value) {
    var node = document.getElementById(id);
    if (!node) { return; }
    node.textContent = value;
    node.className = /过期|失败|中断|错误|无法|限流|超时/.test(value) ? 'warn' : '';
  };
  window.tickerClock = function (iso) {
    if (!iso) { return ''; }
    var date = new Date(iso);
    if (isNaN(date.getTime())) { return ''; }
    var pad = function (n) { return ('0' + n).slice(-2); };
    return pad(date.getHours()) + ':' + pad(date.getMinutes());
  };
}());
