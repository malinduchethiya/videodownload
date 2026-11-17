const $ = id => document.getElementById(id);
let activeVideo = null;
const form = $('video-form');
const analyze = $('analyze');
const alertEl = $('alert');
const resultEl = $('result');

function showError(message) {
  alertEl.textContent = message;
  alertEl.classList.remove('hidden');
}
function clearError() { alertEl.classList.add('hidden'); alertEl.textContent = ''; }
function durationLabel(sec) {
  if (!Number.isFinite(sec) || sec < 0) return 'Duration unknown';
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')} duration`;
}
function fileSize(n) { return n ? ` · ${(n / 1024 / 1024).toFixed(1)} MB est.` : ''; }
async function checkHealth() {
  const dot = $('server-dot'), status = $('server-status');
  try {
    const response = await fetch('/api/health', {cache: 'no-store'});
    if (!response.ok) throw new Error('offline');
    const data = await response.json();
    if (data.status !== 'ok') throw new Error('offline');
    dot.classList.add('ok'); status.textContent = 'API online';
  } catch(e) { dot.classList.add('no'); status.textContent = 'API unavailable'; }
}
form.addEventListener('submit', async e => {
  e.preventDefault(); clearError(); resultEl.classList.add('hidden'); activeVideo = null;
  const url = $('video-url').value.trim();
  analyze.disabled = true; $('analyze-text').textContent = 'Analyzing...';
  try {
    const response = await fetch('/api/info', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({url})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not analyze this link.');
    activeVideo = data;
    $('title').textContent = data.title;
    $('channel').textContent = data.channel;
    $('length').textContent = durationLabel(data.duration);
    const img = $('thumbnail');
    if (data.thumbnail) { img.src = data.thumbnail; img.alt = `Thumbnail for ${data.title}`; }
    else { img.removeAttribute('src'); }
    const quality = $('quality'); quality.replaceChildren();
    for (const fmt of data.formats) {
      const option = new Option(fmt.label + fileSize(fmt.filesize), fmt.id);
      quality.add(option);
    }
    $('download').disabled = !data.formats.length;
    $('format-note').textContent = data.message || 'Your browser should receive an MP4 attachment. Large files, source restrictions or timeouts may interrupt downloads.';
    resultEl.classList.remove('hidden');
    resultEl.scrollIntoView({behavior:'smooth',block:'nearest'});
  } catch (err) { showError(err.message || 'Something went wrong.'); }
  finally { analyze.disabled = false; $('analyze-text').textContent = 'Analyze link'; }
});
$('download').addEventListener('click', () => {
  if (!activeVideo || !$('quality').value) return;
  const qs = new URLSearchParams({url: activeVideo.video_url, format_id: $('quality').value});
  // Same origin response includes Content-Disposition: attachment.
  window.location.href = '/api/download?' + qs.toString();
});
checkHealth();
