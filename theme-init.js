/* Runs before first paint so a saved dark theme never flashes light.
   Loaded from <head>; the page CSP forbids inline scripts. */
try {
  if (window.localStorage.getItem('theme') === 'night') {
    document.documentElement.className = 'night';
  }
} catch (e) {}
