HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>POGLS Control Room</title>
<style>
:root{--bg:#0b0d11;--panel:#121722;--card:#171d2b;--ink:#dfe7f5;--muted:#8ea0be;--accent:#50b7ff;--ok:#38d996;--warn:#f6c85f;--bad:#ff6b81;--border:#25304a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}header{padding:18px 22px;border-bottom:1px solid var(--border);position:sticky;top:0;background:rgba(11,13,17,.96)}main{padding:20px;display:grid;gap:18px}.card{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:16px}.row{display:grid;gap:18px}.row.two{grid-template-columns:1.1fr .9fr}.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.kpi{padding:12px;border-radius:12px;background:var(--card);border:1px solid var(--border)}.kpi .v{font-size:24px;font-weight:700}.kpi .l{color:var(--muted)}.muted{color:var(--muted)}.small{font-size:12px}.table-wrap{max-height:420px;overflow:auto;border:1px solid var(--border);border-radius:12px}table{width:100%;border-collapse:collapse}th,td{padding:10px 12px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}th{position:sticky;top:0;background:#121722}.pill{display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid var(--border);background:var(--card);color:var(--muted);margin:2px 4px 0 0}.state-strong{color:var(--ok)}.state-partial{color:var(--warn)}.state-early{color:var(--bad)}input,select,button{background:#0e1420;color:var(--ink);border:1px solid var(--border);border-radius:10px;padding:8px 10px}button{cursor:pointer}.file-link{color:var(--accent);cursor:pointer;text-decoration:none}.file-link:hover{text-decoration:underline}pre{white-space:pre-wrap;word-break:break-word;background:#0e1420;border:1px solid var(--border);border-radius:12px;padding:12px;max-height:260px;overflow:auto}.flex{display:flex;gap:10px;align-items:center;flex-wrap:wrap}@media (max-width:1100px){.row.two,.kpis{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>POGLS Control Room</h1>
  <p class="muted">Manifest-driven local dashboard for POGLS38 + POGLS4 tracking, file links, and exportable status reports.</p>
</header>
<main>
  <section class="card">
    <div class="flex" style="justify-content:space-between">
      <div>
        <h2>Overview</h2>
        <div class="small muted">Manifest YAML drives repo roles, tracked paths, and cross-repo links.</div>
      </div>
      <div class="flex">
        <select id="repoSelect"></select>
        <input id="fileSearch" placeholder="Filter files/modules…" />
        <button id="refreshBtn">Refresh</button>
        <button id="exportJsonBtn">Export JSON</button>
        <button id="exportMdBtn">Export Markdown</button>
      </div>
    </div>
    <div class="kpis" id="kpis"></div>
  </section>

  <section class="row two">
    <article class="card">
      <h2>Modules</h2>
      <div class="small muted">Score mixes tracked files, tests, docs, runtime hints, roadmap coverage, and cross-repo links.</div>
      <div class="table-wrap"><table><thead><tr><th>Module</th><th>Score</th><th>State</th><th>Tracked</th><th>Files</th><th>Tests</th><th>Roadmap</th><th>X-Repo</th></tr></thead><tbody id="modulesBody"></tbody></table></div>
    </article>
    <article class="card">
      <h2>Repo / Runtime</h2>
      <div id="runtimeList"></div>
      <h3 style="margin-top:18px">Roadmap</h3>
      <div class="table-wrap" style="max-height:220px"><table><thead><tr><th>Status</th><th>Task</th></tr></thead><tbody id="roadmapBody"></tbody></table></div>
    </article>
  </section>

  <section class="row two">
    <article class="card">
      <h2>Files</h2>
      <div class="small muted">Includes, imports, tests, docs, roadmap references, and manifest links are all merged here.</div>
      <div class="table-wrap"><table><thead><tr><th>File</th><th>Module</th><th>Out</th><th>In</th><th>Tests</th><th>Docs/Roadmap</th></tr></thead><tbody id="filesBody"></tbody></table></div>
    </article>
    <article class="card">
      <h2>Dependency Inspector</h2>
      <div id="inspector" class="muted">Click a file to inspect links and export-friendly context.</div>
    </article>
  </section>
</main>
<script>
let SNAP = null; let repoName = null; let selectedFile = null; let ALL = {};
async function getJSON(url, opts){ const r=await fetch(url, opts||{}); return await r.json(); }
function fmtTime(ts){ return ts ? new Date(ts*1000).toLocaleString() : '-'; }
function edgeCount(obj){ return Object.values(obj||{}).reduce((n, arr)=>n+arr.length,0); }
function renderRepoSelect(){ const sel=document.getElementById('repoSelect'); sel.innerHTML=''; Object.keys(SNAP.repos||{}).forEach(name=>{ const o=document.createElement('option'); o.value=name; o.textContent=name; if(name===repoName) o.selected=true; sel.appendChild(o);}); }
function currentRepo(){ const names=Object.keys(SNAP.repos||{}); if(!repoName || !SNAP.repos[repoName]) repoName=names[0]||null; return repoName ? SNAP.repos[repoName] : null; }
function renderKPIs(repo){ const s=repo.summary; const data=[['Repos', SNAP.overview.repo_count],['Files', s.file_count],['Modules', s.module_count],['Roadmap', `${s.roadmap_done}/${s.roadmap_total}`],['Last scan', fmtTime(SNAP.generated_at)]]; document.getElementById('kpis').innerHTML=data.map(([l,v])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join(''); }
function renderModules(repo){ const q=document.getElementById('fileSearch').value.toLowerCase(); const rows=Object.values(repo.modules).filter(m=>!q || m.name.toLowerCase().includes(q)).sort((a,b)=>b.score-a.score).map(m=>`<tr><td><strong>${m.name}</strong></td><td>${m.score}</td><td class="state-${m.state}">${m.state}</td><td>${m.tracked_paths.length}</td><td>${m.files.length}</td><td>${m.tests.length}</td><td>${m.roadmap_done}/${m.roadmap_total}</td><td>${m.cross_repo_links.length}</td></tr>`).join(''); document.getElementById('modulesBody').innerHTML=rows||`<tr><td colspan="8" class="muted">No modules match filter.</td></tr>`; }
function renderRuntime(repo){ const summary=repo.summary; const runtime=`<div class="pill">role: ${summary.role}</div><div class="pill">runtime checks: ${summary.runtime_checks}</div>` + (repo.runtime_checks||[]).map(item=>`<div style="margin-top:8px"><strong>${item.file}</strong> ${item.items.map(x=>`<span class="pill">${x}</span>`).join('')}</div>`).join(''); document.getElementById('runtimeList').innerHTML=runtime || '<div class="muted">No runtime hints.</div>'; document.getElementById('roadmapBody').innerHTML=(repo.roadmap||[]).slice(0,40).map(item=>`<tr><td>${item.done?'✅':'⬜'}</td><td>${item.label}</td></tr>`).join('') || `<tr><td colspan="2" class="muted">No roadmap found.</td></tr>`; }
function renderFiles(repo){ const q=document.getElementById('fileSearch').value.toLowerCase(); const rows=Object.values(repo.files).filter(f=>!q || f.path.toLowerCase().includes(q) || f.module.toLowerCase().includes(q)).sort((a,b)=>edgeCount(b.outgoing)+edgeCount(b.incoming)-edgeCount(a.outgoing)-edgeCount(a.incoming)).slice(0,250).map(f=>`<tr><td><a class="file-link" data-file="${f.id}">${f.path}</a></td><td>${f.module}</td><td>${edgeCount(f.outgoing)}</td><td>${edgeCount(f.incoming)}</td><td>${f.tests.length}</td><td>${f.docs.length+f.roadmap.length}</td></tr>`).join(''); document.getElementById('filesBody').innerHTML=rows||`<tr><td colspan="6" class="muted">No files match filter.</td></tr>`; document.querySelectorAll('[data-file]').forEach(el=>el.onclick=()=>{ selectedFile=el.dataset.file; renderInspector(); }); }
function linkList(ids){ if(!ids||!ids.length) return '<span class="muted">none</span>'; return ids.map(id=>{ const file=ALL[id]; return file ? `<a class="file-link" data-file="${id}">${file.id}</a>` : `<span class="pill">${id}</span>`; }).join('<br/>'); }
function renderInspector(){ const box=document.getElementById('inspector'); const file=selectedFile ? ALL[selectedFile] : null; if(!file){ box.innerHTML='<div class="muted">Click a file to inspect dependencies and cross-repo links.</div>'; return; } const out=Object.entries(file.outgoing||{}).map(([k,v])=>`<h3>Outgoing · ${k}</h3><div>${linkList(v)}</div>`).join(''); const inc=Object.entries(file.incoming||{}).map(([k,v])=>`<h3>Incoming · ${k}</h3><div>${linkList(v)}</div>`).join(''); box.innerHTML=`<div class="small muted">${file.id}</div><h3>${file.path}</h3><div class="pill">module: ${file.module}</div><div class="pill">repo: ${file.repo}</div><pre>${(file.exports||[]).join('\n')||'no exports detected'}</pre><h3>Tests</h3>${linkList(file.tests)}<h3>Docs</h3><pre>${(file.docs||[]).join('\n')||'none'}</pre><h3>Roadmap / Links</h3><pre>${(file.roadmap||[]).join('\n')||'none'}</pre>${out}${inc}`; document.querySelectorAll('#inspector [data-file]').forEach(el=>el.onclick=()=>{ selectedFile=el.dataset.file; renderInspector(); }); }
function renderAll(){ const repo=currentRepo(); renderRepoSelect(); if(!repo) return; renderKPIs(repo); renderModules(repo); renderRuntime(repo); renderFiles(repo); renderInspector(); }
async function load(){ SNAP=await getJSON('/api/scan'); ALL=SNAP.files||{}; renderAll(); }
document.getElementById('repoSelect').addEventListener('change', e=>{ repoName=e.target.value; selectedFile=null; renderAll();});
document.getElementById('fileSearch').addEventListener('input', ()=>renderAll());
document.getElementById('refreshBtn').addEventListener('click', async()=>{ await getJSON('/api/rescan',{method:'POST'}); await load();});
document.getElementById('exportJsonBtn').addEventListener('click', ()=>window.open('/api/export?format=json', '_blank'));
document.getElementById('exportMdBtn').addEventListener('click', ()=>window.open('/api/export?format=markdown', '_blank'));
load();
</script>
</body>
</html>
'''
