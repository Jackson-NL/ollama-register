// Minimal background worker for companion extension
chrome.runtime.onInstalled.addListener(() => {
  console.log('minimal companion installed');
});
