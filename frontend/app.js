const $ = (id) => document.getElementById(id);
const API = (window.CLIPPORT_API_URL || '').replace(/\/+$/, '');
const configured = /^https:\/\/[^\s/]+\.[^\s/]+$/.test(API) && !API.includes('REPLACE-WITH-');
const form = $('video-form');
const analyze = $('analyze');
const alertEl = $('alert');
const resultEl = $('result');
let activeVideo = null;

function showError(message) {
  alertEl.textContent = message;
  alertEl.classList.remove('hidden');
}
function clearError() { alertEl.classList.add('hidden'); alertEl.textContent = ''; }
function durationLabel(sec) {
  if (!Number.isFinite(sec) || sec < 0) return 'Duration unknown';
  return `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')} duration`;
}
async function healthCheck() {
  const dot = $('server-dot'), status = $('server-status');
  if (!configured) {
    dot.classList.add('no'); status.textContent = 'Set API URL in config.js';
    showError('Backend not configured. Edit frontend/config.js with your Render URL, then redeploy Vercel.');
    return;
  }
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90000); // Render Free cold start
    let response;
    try { response = await fetch(`${API}/api/health`, { signal: controller.signal }); }
    finally { clearTimeout(timer); }
    const data = await response.json();
    if (!response.ok || data.status !== 'ok') throw new Error('offline');
    dot.classList.add('ok'); status.textContent = 'Downloader online';
    if (!data.deno || !data.ffmpeg) showError('Backend is missing Deno or FFmpeg. Check the Docker deployment.');
  } catch (e) {
    dot.classList.add('no'); status.textContent = 'Backend unavailable';
  }
}
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearError();
  if (!configured) { showError('Configure the Render backend URL in frontend/config.js first.'); return; }
  resultEl.classList.add('hidden'); activeVideo = null;
  analyze.disabled = true; $('analyze-text').textContent = 'Analyzing...';
  try {
    const response = await fetch(`${API}/api/info`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: $('video-url').value.trim() })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not analyze this URL.');
    activeVideo = data;
    $('title').textContent = data.title;
    $('channel').textContent = data.channel;
    $('length').textContent = durationLabel(data.duration);
    const img = $('thumbnail');
    if (data.thumbnail) { img.src = data.thumbnail; img.alt = `Thumbnail for ${data.title}`; }
    else { img.removeAttribute('src'); }
    const quality = $('quality'); quality.replaceChildren();
    for (const fmt of data.formats) quality.add(new Option(fmt.label, fmt.id));
    $('download').disabled = !data.formats.length;
    $('format-note').textContent = data.message || 'The server will download and merge the selected MP4. Large files may exceed the demo limits.';
    resultEl.classList.remove('hidden');
    resultEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) {
    showError(error.message || 'Unable to contact backend. Check the API URL and CORS FRONTEND_ORIGIN setting.');
  } finally {
    analyze.disabled = false; $('analyze-text').textContent = 'Analyze link';
  }
});
$('download').addEventListener('click', () => {
  if (!activeVideo || !$('quality').value) return;
  const qs = new URLSearchParams({url: activeVideo.video_url, height: $('quality').value});
  window.location.href = `${API}/api/download?${qs.toString()}`;
});
healthCheck();
