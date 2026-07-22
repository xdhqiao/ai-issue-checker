const passwordManagerOverlaySelector = [
  '[data-lastpass-icon-root]',
  '[data-lastpass-root]',
  'iframe[src^="chrome-extension://hdokiejnpimakedhajhdlcegeplioahd/"]',
].join(',');

function removePasswordManagerOverlays() {
  document.querySelectorAll(passwordManagerOverlaySelector).forEach(element => element.remove());
}

removePasswordManagerOverlays();
const passwordManagerObserver = new MutationObserver(removePasswordManagerOverlays);
passwordManagerObserver.observe(document.documentElement, {childList: true, subtree: true});
window.addEventListener('pagehide', () => passwordManagerObserver.disconnect(), {once: true});
