// SES Think Tank — Frontend Application
let ws = null;
let personas = [];
let workflows = {};
let selectedPersonas = ['rook', 'elena', 'kael', 'maya'];
let workflowMode = 'salon';
let currentSession = null;
let turnCount = 0;
let startTime = 0;
let timerInterval = null;
let hitlMode = 'steer';
let hitlHistory = [];
let isPaused = false;
let speakers = new Set();
let currentPhase = '';
let whiteboardData = {};
const personaIcons = {rook:'♟️',elena:'🌸',kael:'⚡',maya:'🔮',jax:'🔥',sage:'🌿'};
const personaColors = {rook:'#6366f1',elena:'#ec4899',kael:'#f59e0b',maya:'#06b6d4',jax:'#ef4444',sage:'#10b981'};
let synergyHistory = {cross_reference_rate:[],friction_level:[],convergence_score:[]};

function switchRightTab(tabName) {
  document.querySelectorAll('.right-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.right-tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelector(`.right-tab[data-tab="${tabName}"]`).classList.add('active');
  document.getElementById('tab-' + tabName).classList.add('active');
}

async function init() {
  const [pRes, wRes] = await Promise.all([fetch('/api/personas'), fetch('/api/workflows')]);
  personas = await pRes.json();
  workflows = await wRes.json();
  renderPersonas();
}

function renderPersonas() {
  const list = document.getElementById('personaList');
  list.innerHTML = personas.map(p => `
    <div class="persona-card ${selectedPersonas.includes(p.id) ? 'selected' : ''}" onclick="togglePersona('${p.id}')">
      <div class="persona-header">
        <span class="persona-icon">${p.icon}</span>
        <div><div class="persona-name">${p.name}</div><div class="persona-title">${p.title}</div></div>
      </div>
      ${p.background ? `<div style="font-size:10px;color:var(--text-dim);margin-top:5px;line-height:1.5;padding-top:5px;border-top:1px solid var(--border);">${p.background}</div>` : ''}
    </div>
  `).join('');
}

function togglePersona(id) {
  if (selectedPersonas.includes(id)) selectedPersonas = selectedPersonas.filter(p => p !== id);
  else selectedPersonas.push(id);
  renderPersonas();
}

function setTopic(text) {
  document.getElementById('topicInput').value = text.replace(/^[^\s]+\s/, '');
}

document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    workflowMode = btn.dataset.mode;
  });
});

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const dot = document.getElementById('connectionDot');
  const text = document.getElementById('connectionText');
  dot.className = 'connection-dot connecting';
  text.textContent = 'Connecting';
  ws = new WebSocket(`${proto}://${location.host}/ws/${Date.now()}`);
  ws.onopen = () => {
    console.log('Connected');
    dot.className = 'connection-dot';
    text.textContent = 'Connected';
  };
  ws.onclose = () => {
    dot.className = 'connection-dot disconnected';
    text.textContent = 'Reconnecting...';
    setTimeout(connectWS, 3000);
  };
  ws.onerror = (e) => console.error('WS error:', e);
  ws.onmessage = (event) => {
    hideTyping();
    const data = JSON.parse(event.data);
    switch (data.type) {
      case 'message': addMessage(data.message); break;
      case 'phase_change': showPhase(data); break;
      case 'evaluation': showEvaluation(data); break;
      case 'deliverable': showDeliverable(data); break;
      case 'session_complete':
        finishConversation(data);
        if (data.synergy_summary) finishSynergyDashboard(data.synergy_summary);
        break;
      case 'synergy_metrics': updateSynergyDashboard(data.metrics, data.turn); break;
      case 'team_recommendation': if (data.analysis) renderTeamAnalysis(data.analysis); break;
      case 'conversation_state': renderStateTracker(data); break;
      case 'whiteboard_update': renderWhiteboard(data.whiteboard); break;
      case 'memory_suggestion': showMemorySuggestion(data); break;
      case 'intervention': addHitlHistoryItem(data); break;
      case 'tool_use': addToolUseIndicator(data); break;
      case 'typing': showTyping(data.persona_name); break;
    }
  };
}

function startConversation() {
  const topic = document.getElementById('topicInput').value;
  if (!topic) return;
  turnCount = 0; speakers.clear(); currentPhase = ''; startTime = Date.now();
  document.getElementById('chatArea').innerHTML = '';
  document.getElementById('topicDisplay').textContent = topic;
  document.getElementById('deliverableArea').innerHTML = '<div class="deliverable-placeholder"><div style="font-size:24px;margin-bottom:6px;">⏳</div>In progress...</div>';
  document.getElementById('startBtn').disabled = true;
  document.getElementById('statTurns').textContent = '0';
  document.getElementById('statSpeakers').textContent = '0';
  document.getElementById('statPhase').textContent = '—';
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    const s = Math.floor((Date.now()-startTime)/1000);
    document.getElementById('statTime').textContent = s<60?`${s}s`:`${Math.floor(s/60)}m ${s%60}s`;
  }, 1000);
  if (workflowMode !== 'salon' && workflows[workflowMode]) renderPhaseBar(workflows[workflowMode].phases);
  currentSession = 'web_' + Date.now();
  hitlHistory = []; isPaused = false;
  document.getElementById('hitlSection').style.display = 'block';
  document.getElementById('hitlHistory').innerHTML = '<div style="font-size:10px;color:var(--text-muted);text-align:center;padding:8px;">No interventions yet.</div>';
  document.getElementById('hitlStatus').className = 'hitl-status running';
  document.getElementById('hitlStatus').textContent = '● Running';
  ws.send(JSON.stringify({type:'start_conversation',session_id:currentSession,topic,personas:[],max_turns:workflows[workflowMode]?.max_turns||30,workflow_mode:workflowMode,auto_team:true}));
}

function addMessage(msg) {
  const chat = document.getElementById('chatArea');
  turnCount++; speakers.add(msg.persona_name);
  document.getElementById('statTurns').textContent = turnCount;
  document.getElementById('statSpeakers').textContent = speakers.size;
  const isRight = ['rook','maya'].includes(msg.persona_id);
  const toolBadges = (msg.tool_uses||[]).map(t => `<span class="tool-badge ${t.error?'error':''}" title="${t.error||t.result||''}">🔧 ${t.tool}</span>`).join('');
  const div = document.createElement('div');
  div.className = `message ${msg.persona_id||''} ${isRight?'right':'left'}`;
  const content = renderMarkdown(msg.content);
  div.innerHTML = `<div class="msg-avatar" style="background:${msg.color}22;border-color:${msg.color}44;">${msg.icon}</div><div><div class="msg-bubble">${content}</div>${toolBadges?`<div class="msg-tools">${toolBadges}</div>`:''}<div class="msg-meta"><span style="color:${msg.color};font-weight:600;">${msg.persona_name}</span>${msg.phase?`<span class="msg-phase-tag">${msg.phase}</span>`:''}<span>${timeAgo(msg.timestamp*1000)}</span><button class="msg-action-btn" onclick="copyMessage(this.closest('.message').querySelector('.msg-bubble').textContent)">📋 Copy</button></div></div>`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}
function addToolUseIndicator(data) {
  const toast = document.createElement('div');
  toast.className = 'tool-toast';
  const isError = !!data.error;
  toast.innerHTML = `<span>${data.icon||'🔧'}</span><strong>${data.persona_name}</strong> used <code style="color:${isError?'#fca5a5':'#a5b4fc'}">${data.tool}</code> ${isError?`<span style="color:#fca5a5">⚠️ ${data.error}</span>`:`<span style="color:var(--text-dim)">→ ${data.result||'done'}</span>`}`;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function showPhase(data) {
  currentPhase = data.phase;
  document.getElementById('statPhase').textContent = data.icon;
  document.querySelectorAll('.phase-step').forEach(step => {
    const sp = step.dataset.phase;
    if (sp === data.phase) { step.classList.add('active'); step.classList.remove('done'); }
    else if (step.classList.contains('active') && sp !== data.phase) { step.classList.remove('active'); step.classList.add('done'); }
  });
  const info = document.getElementById('phaseInfo');
  info.style.display = 'block';
  document.getElementById('phaseName').textContent = `${data.icon} ${data.name}`;
  document.getElementById('phaseDesc').textContent = data.description;
  const speakerNames = data.speakers.map(id => { const p = personas.find(pp=>pp.id===id); return p?`${p.icon} ${p.name}`:id; });
  document.getElementById('phaseSpeakers').textContent = `Speakers: ${speakerNames.join(', ')}`;
}

function renderPhaseBar(phases) {
  const bar = document.getElementById('phaseBar');
  bar.style.display = 'flex';
  bar.innerHTML = phases.map((p,i) => `${i>0?'<span class="phase-arrow">→</span>':''}<div class="phase-step" data-phase="${p.id}"><span>${p.icon}</span><span>${p.name}</span></div>`).join('');
}

function showEvaluation(data) {
  const chat = document.getElementById('chatArea');
  const ev = data.evaluation;
  const div = document.createElement('div');
  div.className = 'eval-badge';
  div.innerHTML = `<div style="display:flex;align-items:center;gap:12px;"><div class="eval-score">${ev.quality_score}/10</div><div><div style="font-weight:600;margin-bottom:2px;">📊 Evaluation (Turn ${data.turn})</div><div class="eval-reason">${ev.reason||''}</div><div style="margin-top:4px;color:${ev.should_continue?'#22c55e':'#ef4444'};">${ev.should_continue?'▶ Continuing...':'⏹ Ended'}</div></div></div>`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function showDeliverable(data) {
  const area = document.getElementById('deliverableArea');
  area.innerHTML = `<div class="panel-title">${data.phase==='finalize'?'✅ Final Deliverable':'📝 Draft Output'}</div><div class="deliverable-content">${renderMarkdown(data.content)}</div><div style="margin-top:6px;font-size:10px;color:var(--text-muted);">By ${data.author} · ${data.phase} phase</div>`;
}

function finishConversation(data) {
  clearInterval(timerInterval);
  document.getElementById('startBtn').disabled = false;
  const chat = document.getElementById('chatArea');
  const div = document.createElement('div');
  div.style.cssText = 'text-align:center;padding:16px;color:var(--text-dim);font-size:12px;';
  div.innerHTML = `<div style="font-size:22px;margin-bottom:6px;">✅</div><div style="font-weight:600;">Conversation Complete</div><div>${data.total_turns} turns · ${Math.round(data.total_time)}s</div>`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  document.querySelectorAll('.phase-step').forEach(s => { s.classList.remove('active'); s.classList.add('done'); });
  // Show export buttons
  document.getElementById('exportRow').style.display = 'flex';
  if (data.whiteboard) {
    renderWhiteboard(data.whiteboard);
    const pins = Object.values(data.whiteboard);
    const area = document.getElementById('deliverableArea');
    const existing = area.querySelector('.deliverable-content');
    if (existing && pins.length > 0) {
      const wbHtml = pins.map(p => `📌 **${p.topic}** — ${p.content} (${p.status}, ${Object.keys(p.votes||{}).length} votes)`).join('\n');
      existing.innerHTML += `<hr style="border:none;border-top:1px solid var(--border);margin:10px 0;"><strong>📋 Whiteboard Summary</strong><br>${renderMarkdown(wbHtml)}`;
    }
  }
}

function escapeHtml(text) { const d = document.createElement('div'); d.textContent = text; return d.innerHTML; }

function renderMarkdown(text) {
  let h = escapeHtml(text);
  h = h.replace(/```([\s\S]*?)```/g, '<pre style="background:var(--bg);padding:8px;border-radius:6px;overflow-x:auto;margin:6px 0;font-size:11px;border:1px solid var(--border);"><code>$1</code></pre>');
  h = h.replace(/`([^`]+)`/g, '<code style="background:var(--bg);padding:2px 5px;border-radius:3px;font-size:11px;border:1px solid var(--border);">$1</code>');
  h = h.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  h = h.replace(/~~([^~]+)~~/g, '<del>$1</del>');
  h = h.replace(/^## (.+)$/gm, '<h3 style="margin:10px 0 4px;font-size:14px;color:var(--accent);">$1</h3>');
  h = h.replace(/^### (.+)$/gm, '<h4 style="margin:8px 0 3px;font-size:12px;color:var(--text);">$1</h4>');
  h = h.replace(/^&gt; (.+)$/gm, '<blockquote style="border-left:3px solid var(--accent);padding-left:10px;margin:6px 0;color:var(--text-dim);font-style:italic;">$1</blockquote>');
  h = h.replace(/^---$/gm, '<hr style="border:none;border-top:1px solid var(--border);margin:10px 0;">');
  h = h.replace(/\n/g, '<br>');
  return h;
}

function timeAgo(ts) { const d=(Date.now()-ts)/1000; if(d<5) return 'now'; if(d<60) return `${Math.floor(d)}s ago`; return `${Math.floor(d/60)}m ago`; }

async function analyzeTeam() {
  const topic = document.getElementById('topicInput').value;
  if (!topic) return;
  const panel = document.getElementById('teamAnalysisPanel');
  panel.style.display = 'block';
  document.getElementById('teamPersonas').innerHTML = '<div class="team-loading">Analyzing topic...</div>';
  document.getElementById('teamReasoning').textContent = '';
  document.getElementById('useTeamBtn').style.display = 'none';
  try {
    const resp = await fetch('/api/teams/analyze', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic,workflow_mode:workflowMode})});
    const data = await resp.json();
    renderTeamAnalysis(data);
  } catch(e) { document.getElementById('teamPersonas').innerHTML = '<div style="color:#ef4444;font-size:12px;">Analysis failed.</div>'; }
}

function renderTeamAnalysis(data) {
  document.getElementById('teamDomain').textContent = data.domain||'—';
  document.getElementById('teamComplexity').textContent = data.complexity||'—';
  const chips = personas.map(p => {
    const rec = (data.recommended_personas||[]).includes(p.id);
    const exc = (data.excluded_personas||[]).includes(p.id);
    if (!rec && !exc) return '';
    return `<div class="team-persona-chip ${exc?'excluded':''}" style="${exc?'':'border-color:'+(personaColors[p.id]||'#333')+'44;'}"><span>${p.icon||personaIcons[p.id]||'?'}</span><span>${p.name}</span>${exc?'<span style="font-size:9px;color:var(--text-muted);">(excluded)</span>':''}</div>`;
  }).join('');
  document.getElementById('teamPersonas').innerHTML = chips;
  document.getElementById('teamReasoning').textContent = data.reasoning||'';
  document.getElementById('useTeamBtn').style.display = 'inline-block';
}

function useRecommendedTeam() {
  const topic = document.getElementById('topicInput').value;
  if (!topic) return;
  document.getElementById('teamAnalysisPanel').style.display = 'none';
  turnCount=0; speakers.clear(); currentPhase=''; startTime=Date.now();
  document.getElementById('chatArea').innerHTML = '';
  document.getElementById('topicDisplay').textContent = topic;
  document.getElementById('deliverableArea').innerHTML = '<div class="deliverable-placeholder"><div style="font-size:24px;margin-bottom:6px;">⏳</div>In progress...</div>';
  document.getElementById('startBtn').disabled = true;
  document.getElementById('statTurns').textContent = '0';
  document.getElementById('statSpeakers').textContent = '0';
  document.getElementById('statPhase').textContent = '—';
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    const s = Math.floor((Date.now()-startTime)/1000);
    document.getElementById('statTime').textContent = s<60?`${s}s`:`${Math.floor(s/60)}m ${s%60}s`;
  }, 1000);
  if (workflowMode !== 'salon' && workflows[workflowMode]) renderPhaseBar(workflows[workflowMode].phases);
  ws.send(JSON.stringify({type:'start_conversation',session_id:'web_'+Date.now(),topic,personas:[],max_turns:workflows[workflowMode]?.max_turns||30,workflow_mode:workflowMode,auto_team:true}));
}

function renderStateTracker(state) {
  const section = document.getElementById('stateSection');
  if (!state||(!state.current_topic&&!state.dominant_theme)) { section.style.display='none'; return; }
  section.style.display = 'block';
  document.getElementById('stateTopic').textContent = state.current_topic||'—';
  document.getElementById('stateWorkflow').textContent = `${workflows[workflowMode]?.name||workflowMode} › ${state.phase_name||'Freeform'}`;
  const pct = Math.round((state.phase_progress||0)*100);
  document.getElementById('statePhaseFill').style.width = pct+'%';
  document.getElementById('statePhaseLabel').textContent = pct+'%';
  const spk = document.getElementById('stateActiveSpeakers');
  spk.innerHTML = (state.active_speakers||[]).length>0 ? state.active_speakers.map(s=>`<div class="state-speaker-icon active" style="border-color:${s.color};background:${s.color}22;" title="${s.name}">${s.icon}</div>`).join('') : '<span style="font-size:10px;color:var(--text-muted);">—</span>';
  document.getElementById('stateTheme').textContent = state.dominant_theme||'—';
  const tl = document.getElementById('stateTopicsList');
  tl.innerHTML = (state.topics_covered||[]).length>0 ? state.topics_covered.map(t=>`<div class="state-topic-item"><span>${escapeHtml(t.topic)}</span><span class="state-topic-count">${t.turn_count}</span></div>`).join('') : '<div style="font-size:10px;color:var(--text-muted);padding:3px 6px;">No topics yet.</div>';
}

function renderWhiteboard(wb) {
  whiteboardData = wb||{};
  const section = document.getElementById('whiteboardSection');
  const pins = Object.values(whiteboardData);
  if (!pins.length) { section.style.display='none'; return; }
  section.style.display = 'block';
  const approved = pins.filter(p=>p.status==='approved').length;
  const pending = pins.filter(p=>p.status==='pending').length;
  document.getElementById('whiteboardSummary').textContent = `${pins.length} pins · ${approved} approved · ${pending} pending`;
  document.getElementById('whiteboardPins').innerHTML = pins.map(pin => {
    const vc = {approve:0,reject:0,neutral:0};
    Object.values(pin.votes||{}).forEach(v => { if(vc[v]!==undefined) vc[v]++; });
    const voteBtns = ['approve','reject','neutral'].map(v => {
      const active = Object.values(pin.votes||{}).includes(v)?` active-${v}`:'';
      const icons = {approve:'✅',reject:'❌',neutral:'⏳'};
      return `<button class="vote-btn${active}" onclick="event.stopPropagation();castVote('${pin.id}','${v}')">${icons[v]}<span class="vote-count">${vc[v]}</span></button>`;
    }).join('');
    const statusClass = `status-${pin.status}`;
    const statusLabels = {pending:'Pending',approved:'Approved',rejected:'Rejected',discussed:'Discussed'};
    const authorIcon = personaIcons[pin.author]||'📌';
    const authorColor = personaColors[pin.author]||'var(--text)';
    const commentsHtml = (pin.comments||[]).map(c => `<div class="comment"><span class="comment-author">${personaIcons[c.author]||'💬'} ${c.author}</span> ${escapeHtml(c.text)}</div>`).join('');
    return `<div class="pin-card" data-pin-id="${pin.id}" onclick="togglePinExpand(this)"><div class="pin-header"><span class="pin-author"><span style="color:${authorColor}">${authorIcon}</span> ${pin.author}</span><span class="pin-status-badge ${statusClass}">${statusLabels[pin.status]||pin.status}</span></div><div class="pin-topic">${escapeHtml(pin.topic)}</div><div class="pin-content">${escapeHtml(pin.content)}</div><div class="pin-actions">${voteBtns}</div><div class="pin-comments">${commentsHtml}<div class="comment-input-area"><input class="comment-input" placeholder="Comment..." onkeydown="if(event.key==='Enter')addComment('${pin.id}',this)"><button class="comment-btn" onclick="addComment('${pin.id}',this.previousElementSibling)">Send</button></div></div></div>`;
  }).join('');
}

function togglePinExpand(el) { el.classList.toggle('expanded'); }
function castVote(pinId, vote) { if(!currentSession) return; fetch(`/api/sessions/${currentSession}/whiteboard/pins/${pinId}/vote`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({persona_id:document.getElementById('votePersonaSelect')?.value||'user',vote})}).catch(()=>{}); }
function addComment(pinId, input) { if(!currentSession||!input.value.trim()) return; fetch(`/api/sessions/${currentSession}/whiteboard/pins/${pinId}/comment`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({author:document.getElementById('votePersonaSelect')?.value||'user',text:input.value.trim()})}).then(()=>{input.value='';}).catch(()=>{}); }
function showPinIdeaDialog() {
  const topic = prompt('Pin topic:'); if(!topic) return;
  const content = prompt('Pin content:'); if(!content) return;
  const author = document.getElementById('votePersonaSelect')?.value||'user';
  if(ws&&ws.readyState===WebSocket.OPEN&&currentSession) ws.send(JSON.stringify({type:'pin_idea',session_id:currentSession,topic,content,author}));
  else if(currentSession) fetch(`/api/sessions/${currentSession}/whiteboard/pin`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic,content,author})}).catch(()=>{});
}
document.getElementById('pinIdeaBtn')?.addEventListener('click', showPinIdeaDialog);

function updateSynergyDashboard(metrics, turn) {
  document.getElementById('synergySection').style.display = 'block';
  const badge = document.getElementById('synergyBadge');
  const healthMap = {green:'● Healthy',yellow:'● Moderate',red:'● Attention'};
  badge.textContent = healthMap[metrics.health]||'● Unknown';
  badge.className = 'synergy-badge '+(metrics.health||'green');
  synergyHistory.cross_reference_rate.push(metrics.cross_reference_rate);
  synergyHistory.friction_level.push(metrics.friction_level);
  synergyHistory.convergence_score.push(metrics.convergence_score);
  drawSparkline('sparklineCrossRef', synergyHistory.cross_reference_rate, '#22c55e');
  drawSparkline('sparklineFriction', synergyHistory.friction_level, '#f59e0b');
  drawSparkline('sparklineConvergence', synergyHistory.convergence_score, '#6366f1');
  document.getElementById('valCrossRef').textContent = Math.round(metrics.cross_reference_rate*100)+'%';
  document.getElementById('valFriction').textContent = Math.round(metrics.friction_level*100)+'%';
  document.getElementById('valConvergence').textContent = Math.round(metrics.convergence_score*100)+'%';
  document.getElementById('ideaDiversity').textContent = metrics.idea_diversity||0;
  if (metrics.participation_counts) drawPieChart('participationPie', metrics.participation_counts);
  document.getElementById('interveneInput').disabled = false;
  document.getElementById('interveneBtn').disabled = false;
}

function drawSparkline(canvasId, values, color) {
  const canvas = document.getElementById(canvasId);
  if(!canvas||values.length<2) return;
  const ctx = canvas.getContext('2d'); const w=canvas.width, h=canvas.height;
  ctx.clearRect(0,0,w,h);
  const max=Math.max(1,...values), min=Math.min(0,...values), range=max-min||1;
  const step = w/(values.length-1);
  ctx.beginPath(); ctx.strokeStyle=color; ctx.lineWidth=1.5; ctx.lineJoin='round';
  values.forEach((v,i) => { const x=i*step, y=h-((v-min)/range)*(h-2)-1; i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); });
  ctx.stroke();
  const last=values.length-1; ctx.lineTo(last*step,h); ctx.lineTo(0,h); ctx.closePath();
  ctx.fillStyle=color+'22'; ctx.fill();
}

function drawPieChart(canvasId, counts) {
  const canvas = document.getElementById(canvasId); if(!canvas) return;
  const ctx = canvas.getContext('2d'); const w=canvas.width, h=canvas.height;
  const cx=w/2, cy=h/2, outerR=Math.min(cx,cy)-1, innerR=outerR*0.55;
  ctx.clearRect(0,0,w,h);
  const total = Object.values(counts).reduce((a,b)=>a+b,0);
  if(total===0) return;
  let angle = -Math.PI/2;
  Object.entries(counts).filter(([,v])=>v>0).forEach(([pid,count]) => {
    const slice = (count/total)*Math.PI*2;
    ctx.beginPath(); ctx.arc(cx,cy,outerR,angle,angle+slice); ctx.arc(cx,cy,innerR,angle+slice,angle,true);
    ctx.closePath(); ctx.fillStyle=personaColors[pid]||'#666'; ctx.fill();
    angle += slice;
  });
  ctx.fillStyle='#e0e0e8'; ctx.font='bold 10px Inter,sans-serif'; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText(total,cx,cy);
}

function finishSynergyDashboard(summary) { if(summary.final_metrics) updateSynergyDashboard(summary.final_metrics,'final'); }

function intervene() {
  const input = document.getElementById('interveneInput');
  const msg = input.value.trim(); if(!msg) return;
  if(ws&&ws.readyState===WebSocket.OPEN&&currentSession) { ws.send(JSON.stringify({type:'intervene',session_id:currentSession,message:msg})); input.value=''; }
  else if(currentSession) { fetch(`/api/sessions/${currentSession}/intervene`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})}).then(()=>{input.value='';}).catch(()=>{}); }
}
document.getElementById('interveneBtn')?.addEventListener('click', intervene);
document.getElementById('interveneInput')?.addEventListener('keydown', e => { if(e.key==='Enter') intervene(); });

function showMemorySuggestion(data) {
  if(!data.match_count) return;
  document.getElementById('memoryBadgeRow').innerHTML = `<span class="badge-chip amber" onclick="searchMemory()">${data.message}</span>`;
  if(data.similar_sessions) updateMemoryCount(data.match_count);
}

function updateMemoryCount(count) { document.getElementById('memoryCount').textContent = `${count} session${count!==1?'s':''}`; }

async function searchMemory() {
  const query = document.getElementById('memorySearchInput').value.trim();
  const container = document.getElementById('memoryResults');
  if(!query) { container.innerHTML='<div class="empty-state">Enter a search term.</div>'; return; }
  document.getElementById('memoryBadgeRow').innerHTML = '';
  try {
    const insightsResp = await fetch(`/api/memory/insights/${encodeURIComponent(query)}`);
    const insights = await insightsResp.json();
    if(insights.session_count > 0) {
      const badgeRow = document.getElementById('memoryBadgeRow');
      badgeRow.innerHTML = `<span class="badge-chip amber">${insights.session_count} similar sessions</span>`;
      if(insights.persona_frequency) Object.entries(insights.persona_frequency).slice(0,3).forEach(([pid,count]) => {
        badgeRow.innerHTML += `<span class="badge-chip accent">${personaIcons[pid]||'•'} ×${count}</span>`;
      });
    }
  } catch(e) {}
  container.innerHTML = '<div class="empty-state">Searching...</div>';
  try {
    const resp = await fetch(`/api/memory/sessions?topic=${encodeURIComponent(query)}`);
    const sessions = await resp.json();
    if(!sessions.length) { container.innerHTML='<div class="empty-state">No matching sessions found.</div>'; return; }
    renderMemorySessions(sessions);
  } catch(e) { container.innerHTML='<div class="empty-state">Search failed.</div>'; }
}

function renderMemorySessions(sessions) {
  const container = document.getElementById('memoryResults');
  container.innerHTML = sessions.map(s => {
    const pids = s.persona_ids||[];
    const chips = pids.filter(Boolean).map(pid => `<span class="persona-chip" style="border-color:${personaColors[pid]||'var(--border)'}44;">${personaIcons[pid]||'•'} ${pid}</span>`).join('');
    const dateStr = s.started_at ? new Date(s.started_at*1000).toLocaleDateString() : '—';
    return `<div class="info-card" onclick="toggleMemoryCard(this,'${s.session_id}')"><div class="info-card-header"><span class="info-card-title">${s.topic||'Untitled'}</span><span class="info-card-badge">${s.workflow_mode||'—'}</span></div><div class="info-card-meta">${dateStr}${s.turn_count?` · ${s.turn_count} turns`:''}</div><div class="persona-chips">${chips}</div><div class="info-card-body" id="memorySummary_${s.session_id}">${s.summary||'No summary.'}</div><div class="info-card-body" id="memoryDeliverable_${s.session_id}"></div></div>`;
  }).join('');
}

async function toggleMemoryCard(el, sessionId) {
  const expanded = el.classList.contains('expanded');
  el.classList.toggle('expanded');
  if(!expanded) {
    const deliverableDiv = document.getElementById(`memoryDeliverable_${sessionId}`);
    if(!deliverableDiv.dataset.loaded) {
      try {
        const resp = await fetch(`/api/memory/session/${sessionId}`);
        const data = await resp.json();
        if(data.deliverable) { deliverableDiv.textContent = data.deliverable; deliverableDiv.dataset.loaded = '1'; }
        if(data.pins && data.pins.length > 0) {
          const sumDiv = document.getElementById(`memorySummary_${sessionId}`);
          const pinText = data.pins.map(p=>`📌 ${p.topic}: ${p.content}`).join('\n');
          sumDiv.innerHTML = data.summary ? data.summary+'\n\n📋 Pins:\n'+pinText : '📋 Pins:\n'+pinText;
        }
      } catch(e) {}
    }
  }
}

async function checkMemoryOnTopicInput() {
  const topic = document.getElementById('topicInput').value.trim();
  if(!topic||topic.length<5) return;
  try {
    const resp = await fetch(`/api/memory/sessions?topic=${encodeURIComponent(topic)}`);
    const sessions = await resp.json();
    updateMemoryCount(sessions.length);
    if(sessions.length > 0) renderMemorySessions(sessions);
  } catch(e) {}
}

let memoryCheckTimer = null;
document.getElementById('topicInput').addEventListener('input', () => {
  clearTimeout(memoryCheckTimer);
  memoryCheckTimer = setTimeout(checkMemoryOnTopicInput, 800);
});

function sendHitlIntervention() {
  const input = document.getElementById('hitlInput');
  const msg = input.value.trim(); if(!msg||!currentSession) return;
  ws.send(JSON.stringify({type:'intervene',session_id:currentSession,mode:hitlMode,message:msg,target:''}));
  if(hitlMode==='pause') { isPaused=true; document.getElementById('hitlStatus').className='hitl-status paused'; document.getElementById('hitlStatus').textContent='⏸ Paused'; }
  else if(hitlMode==='resume') { isPaused=false; document.getElementById('hitlStatus').className='hitl-status running'; document.getElementById('hitlStatus').textContent='● Running'; }
  addHitlHistoryItem({mode:hitlMode,message:msg,target:'',id:'local_'+Date.now(),timestamp:Date.now()/1000,session_id:currentSession});
  input.value = '';
}

function addHitlHistoryItem(data) {
  const container = document.getElementById('hitlHistory');
  if(container.textContent.includes('No interventions')) container.innerHTML = '';
  const time = new Date(data.timestamp*1000);
  const timeStr = time.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const item = document.createElement('div');
  item.className = 'hitl-history-item';
  item.innerHTML = `<span class="hitl-history-mode ${data.mode}">${data.mode}</span><span class="hitl-history-msg">${data.message}</span><span class="hitl-history-time">${timeStr}</span>`;
  container.appendChild(item);
  container.scrollTop = container.scrollHeight;
}

document.querySelectorAll('.hitl-mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.hitl-mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active'); hitlMode = btn.dataset.mode;
  });
});
document.getElementById('hitlSend').addEventListener('click', sendHitlIntervention);
document.getElementById('hitlInput').addEventListener('keydown', e => { if(e.key==='Enter') sendHitlIntervention(); });

// ─── Boot ───
init();
connectWS();
(async function loadMemoryCount() {
  try { const resp = await fetch('/api/memory/sessions?topic='); const sessions = await resp.json(); updateMemoryCount(sessions.length); } catch(e) {}
})();

// ─── KEYBOARD SHORTCUTS ───
document.addEventListener('keydown', e => {
  // Cmd/Ctrl + Enter to start conversation
  if((e.metaKey||e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); startConversation(); }
  // Cmd/Ctrl + , for settings
  if((e.metaKey||e.ctrlKey) && e.key === ',') { e.preventDefault(); toggleSettings(); }
  // Cmd/Ctrl + K to focus topic input
  if((e.metaKey||e.ctrlKey) && e.key === 'k') { e.preventDefault(); document.getElementById('topicInput').focus(); }
  // Cmd/Ctrl + T to toggle theme
  if((e.metaKey||e.ctrlKey) && e.key === 't') { e.preventDefault(); toggleTheme(); }
  // Escape to close modals
  if(e.key === 'Escape') {
    document.getElementById('settingsModal').classList.remove('visible');
    document.getElementById('teamAnalysisPanel').style.display = 'none';
    closeMobilePanels();
  }
});

// ─── THEME TOGGLE ───
function toggleTheme() {
  document.body.classList.toggle('light');
  const isLight = document.body.classList.contains('light');
  document.querySelector('.theme-toggle').textContent = isLight ? '☀️' : '🌙';
  localStorage.setItem('theme', isLight ? 'light' : 'dark');
  showToast(isLight ? 'Light theme' : 'Dark theme', '');
}
// Restore saved theme
if(localStorage.getItem('theme') === 'light') {
  document.body.classList.add('light');
  document.querySelector('.theme-toggle') && (document.querySelector('.theme-toggle').textContent = '☀️');
}

// ─── MOBILE PANELS ───
function toggleMobilePanel(side) {
  const panel = document.querySelector(side === 'left' ? '.left-panel' : '.right-panel');
  const overlay = document.getElementById('mobileOverlay');
  panel.classList.toggle('mobile-open');
  overlay.classList.toggle('active');
}
function closeMobilePanels() {
  document.querySelector('.left-panel')?.classList.remove('mobile-open');
  document.querySelector('.right-panel')?.classList.remove('mobile-open');
  document.getElementById('mobileOverlay')?.classList.remove('active');
}

// ─── TYPING INDICATOR ───
let typingTimeout = null;
function showTyping(personaName) {
  const indicator = document.getElementById('typingIndicator');
  const text = document.getElementById('typingText');
  text.textContent = personaName ? `${personaName} is thinking...` : 'Thinking...';
  indicator.classList.add('visible');
  clearTimeout(typingTimeout);
  typingTimeout = setTimeout(hideTyping, 10000);
}
function hideTyping() {
  document.getElementById('typingIndicator').classList.remove('visible');
  clearTimeout(typingTimeout);
}

// ─── TOAST NOTIFICATIONS ───
function showToast(message, type = '') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</span> ${message}`;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.animation = 'toastOut 0.3s ease forwards'; setTimeout(() => toast.remove(), 300); }, 3000);
}

// ─── EXPORT FUNCTIONS ───
function exportMarkdown() {
  const messages = document.querySelectorAll('.message');
  let md = '';
  messages.forEach(msg => {
    const name = msg.querySelector('.msg-meta span:first-child')?.textContent || 'Unknown';
    const content = msg.querySelector('.msg-bubble')?.textContent || '';
    md += `### ${name}\n\n${content}\n\n---\n\n`;
  });
  downloadFile(`think-tank-${Date.now()}.md`, md);
  showToast('Exported as Markdown', 'success');
}

function exportJSON() {
  const messages = [];
  document.querySelectorAll('.message').forEach(msg => {
    const name = msg.querySelector('.msg-meta span:first-child')?.textContent || 'Unknown';
    const content = msg.querySelector('.msg-bubble')?.textContent || '';
    messages.push({speaker: name, content});
  });
  downloadFile(`think-tank-${Date.now()}.json`, JSON.stringify({topic: document.getElementById('topicDisplay').textContent, messages, exported_at: new Date().toISOString()}, null, 2));
  showToast('Exported as JSON', 'success');
}

function copyDeliverable() {
  const content = document.querySelector('.deliverable-content')?.textContent;
  if(content) {
    navigator.clipboard.writeText(content).then(() => showToast('Copied to clipboard', 'success'));
  }
}

function downloadFile(filename, content) {
  const blob = new Blob([content], {type: 'text/plain'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ─── COPY MESSAGE ───
function copyMessage(text) {
  navigator.clipboard.writeText(text).then(() => showToast('Copied', 'success'));
}

// ─── SESSION HISTORY ───
let sessionHistory = [];
async function loadSessionHistory() {
  try {
    const resp = await fetch('/api/sessions');
    const sessions = await resp.json();
    sessionHistory = sessions.slice(0, 10);
    renderSessionHistory();
  } catch(e) {}
}
function renderSessionHistory() {
  const container = document.getElementById('sessionHistoryList');
  if(!container) return;
  if(!sessionHistory.length) { container.innerHTML = '<div class="empty-state">No sessions yet.</div>'; return; }
  container.innerHTML = sessionHistory.map(s => {
    const isActive = currentSession === s.session_id;
    const date = s.started_at ? new Date(s.started_at * 1000).toLocaleDateString() : '';
    return `<div class="session-item ${isActive?'active':''}" onclick="loadSession('${s.session_id}')"><div class="session-topic">${s.topic||'Untitled'}</div><div class="session-meta">${date} · ${s.turn_count||0} turns</div></div>`;
  }).join('');
}
async function loadSession(sessionId) {
  try {
    const resp = await fetch(`/api/sessions/${sessionId}/messages`);
    const messages = await resp.json();
    document.getElementById('chatArea').innerHTML = '';
    messages.forEach(msg => addMessage(msg));
    currentSession = sessionId;
    renderSessionHistory();
  } catch(e) { showToast('Failed to load session', 'error'); }
}

// Load session history on boot
loadSessionHistory();

// ─── TOOL PLUGINS ───
function loadTools() {
  fetch('/api/tools').then(r=>r.json()).then(data => {
    document.getElementById('toolCount').textContent = data.total+' tools';
    const list = document.getElementById('toolList');
    if(!data.tools.length) { list.innerHTML='<div class="empty-state">No tools loaded.</div>'; return; }
    list.innerHTML = data.tools.map(t => `<div class="info-card" style="cursor:default;"><div class="info-card-header"><div class="info-card-title">${t.name}</div><span class="info-card-badge">${t.execution_type||'built-in'}</span></div><div style="font-size:11px;color:var(--text-dim);margin-top:3px;">${t.description}</div>${t.parameters.length?`<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">Params: ${t.parameters.join(', ')}</div>`:''}</div>`).join('');
  }).catch(()=>document.getElementById('toolCount').textContent='Error');
}
function showCreateToolForm() { document.getElementById('createToolForm').style.display = 'block'; }
function createTool() {
  const name=document.getElementById('toolName').value.trim();
  const desc=document.getElementById('toolDesc').value.trim();
  const execType=document.getElementById('toolExecType').value;
  const code=document.getElementById('toolCode').value.trim();
  if(!name||!desc||!code) { alert('Please fill in all fields'); return; }
  const exec = {};
  if(execType==='python') exec.code=code; else if(execType==='shell') exec.command=code; else exec.url=code;
  fetch('/api/tools',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description:desc,parameters:[],execution:exec,timeout:30,sandbox:true})})
    .then(r=>r.json()).then(()=>{document.getElementById('createToolForm').style.display='none';document.getElementById('toolName').value='';document.getElementById('toolDesc').value='';document.getElementById('toolCode').value='';loadTools();}).catch(err=>alert('Error: '+err));
}
function reloadTools() { fetch('/api/tools/reload',{method:'POST'}).then(()=>loadTools()); }

// ─── KNOWLEDGE ───
function loadKnowledge() {
  fetch('/api/knowledge').then(r=>r.json()).then(data => {
    document.getElementById('knowledgeCount').textContent = data.length+' personas';
    const list = document.getElementById('knowledgeList');
    if(!data.length) { list.innerHTML='<div class="empty-state">No knowledge loaded yet.</div>'; return; }
    list.innerHTML = data.map(p => `<div class="info-card" onclick="viewKnowledge('${p.persona_id}')"><div class="info-card-header"><div class="info-card-title">${p.persona_id}</div><span class="info-card-badge">${p.book_count} books${p.has_memories?' + mem':''}</span></div></div>`).join('');
  }).catch(()=>document.getElementById('knowledgeCount').textContent='Error');
}
function viewKnowledge(personaId) {
  fetch('/api/knowledge/'+personaId).then(r=>r.json()).then(data => {
    let html = '<div style="margin-bottom:8px;"><button class="btn-secondary" onclick="loadKnowledge()" style="font-size:10px;padding:3px 8px;">← Back</button></div>';
    if(data.books.length) {
      html += '<div style="font-size:11px;font-weight:600;margin-bottom:4px;">📖 Books:</div>';
      data.books.forEach(b => { html += `<div class="info-card" style="cursor:default;"><div class="info-card-title" style="font-size:11px;">${b.title}</div>${b.key_insights.length?`<div style="font-size:10px;color:var(--text-dim);margin-top:2px;">${b.key_insights.slice(0,3).map(i=>'• '+i).join('<br>')}</div>`:''}</div>`; });
    }
    if(data.memories.length) {
      html += '<div style="font-size:11px;font-weight:600;margin:6px 0 4px;">🧠 Memories:</div>';
      data.memories.slice(-10).forEach(m => { html += `<div style="font-size:10px;padding:3px 0;border-bottom:1px solid var(--border);"><span style="color:var(--text-muted);">${m.date||''}</span> ${m.insight}${m.source?`<div style="font-size:9px;color:var(--text-muted);">from ${m.source}</div>`:''}</div>`; });
    }
    if(!data.books.length&&!data.memories.length) html += '<div class="empty-state">No knowledge yet.</div>';
    document.getElementById('knowledgeList').innerHTML = html;
  });
}
loadTools();
loadKnowledge();

// ─── SESSION INTELLIGENCE ───
function loadIntelligence() {
  fetch('/api/intelligence/summary').then(r=>r.json()).then(data => {
    document.getElementById('intelligenceCount').textContent = data.total_insights+' insights';
    const summary = document.getElementById('intelligenceSummary');
    if(data.total_insights === 0) summary.innerHTML='<div class="empty-state">Insights appear after sessions complete.</div>';
    else {
      let catHtml = Object.entries(data.by_category).map(([cat,count]) => `<span class="badge-chip">${cat}: ${count}</span>`).join(' ');
      summary.innerHTML = `<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">Sessions: ${data.sessions_with_insights}<br>${catHtml}</div>`;
    }
    fetch('/api/intelligence/insights?limit=5').then(r=>r.json()).then(insights => {
      const list = document.getElementById('intelligenceInsights');
      if(!insights.length) return;
      list.innerHTML = insights.map(ins => `<div class="info-card" style="cursor:default;"><div class="info-card-header"><div class="info-card-title" style="font-size:11px;">${ins.session_topic}</div><span class="info-card-badge">${ins.category}</span></div><div style="font-size:10px;color:var(--text-dim);margin-top:3px;">${ins.insight.substring(0,150)}...</div></div>`).join('');
    });
  }).catch(()=>document.getElementById('intelligenceCount').textContent='0 insights');
}
loadIntelligence();

// ─── EVALUATION DASHBOARD ───
function loadEvalDashboard() {
  fetch('/api/eval/dashboard').then(r=>r.json()).then(data => {
    document.getElementById('evalCount').textContent = data.total_sessions_analyzed+' sessions';
    const summary = document.getElementById('evalSummary');
    if(data.total_sessions_analyzed === 0) summary.innerHTML='<div class="empty-state">Evaluation data appears after sessions.</div>';
    else summary.innerHTML = `<div style="font-size:11px;color:var(--text-dim);margin-bottom:8px;">Avg quality: <strong style="color:var(--accent);">${data.average_quality}</strong></div>`;
    const dims = document.getElementById('evalDimensions');
    const dimLabels = {emotional_presence:'💜 Emotional',depth:'🔵 Depth',synergy:'🟢 Synergy',originality:'🟡 Originality',clarity:'⚪ Clarity'};
    let dimHtml = '';
    for(const [dim,val] of Object.entries(data.dimension_averages)) {
      const pct = Math.round(val*100);
      dimHtml += `<div class="eval-dim"><div class="eval-dim-header"><span class="eval-dim-label">${dimLabels[dim]||dim}</span><span class="eval-dim-value">${pct}%</span></div><div class="progress-bar"><div class="progress-fill" style="width:${pct}%;background:var(--accent);"></div></div></div>`;
    }
    dims.innerHTML = dimHtml;
  }).catch(()=>document.getElementById('evalCount').textContent='0 sessions');
}
loadEvalDashboard();

// ─── SETTINGS MODAL ───
function toggleSettings() {
  const modal = document.getElementById('settingsModal');
  if(modal.classList.contains('visible')) modal.classList.remove('visible');
  else { modal.classList.add('visible'); loadSettings(); }
}

function loadSettings() {
  fetch('/api/settings/provider-env').then(r=>r.json()).then(env => {
    if(env && env.provider) {
      document.getElementById('settingsProviderInfo').innerHTML = `<strong>${env.provider}</strong> — ${env.model||'default'}<br>Base: ${env.base_url||'N/A'} | Temp: ${env.temperature} | Max: ${env.max_tokens}`;
    } else {
      throw new Error('No provider data');
    }
  }).catch(()=>{
    document.getElementById('settingsProviderInfo').innerHTML = `<strong>Local (LM Studio)</strong> — Default model<br>Configured via .env file`;
  });
  fetch('/api/settings/providers').then(r=>r.json()).then(providers => {
    fetch('/api/settings/config').then(r=>r.json()).then(config => {
      document.getElementById('settingsProviders').innerHTML = providers.map(p => {
        const saved = config.providers.find(c=>c.provider_name===p.id);
        const isActive = saved ? saved.is_enabled : false;
        const isDefault = saved ? saved.is_default : false;
        return `<div class="modal-provider-card"><div><div class="modal-provider-name">${p.name} ${isDefault?'⭐':''} ${isActive?'✅':''}</div><div class="modal-provider-desc">${p.description} (${p.type})</div></div>${!isDefault?`<button class="btn-secondary" onclick="setDefaultProvider('${p.id}')" style="font-size:10px;padding:3px 8px;">Set Default</button>`:'<span style="font-size:9px;color:var(--accent);padding:3px 8px;">Default</span>'}</div>`;
      }).join('');
    });
  }).catch(()=>{
    document.getElementById('settingsProviders').innerHTML = '<div style="font-size:11px;color:var(--text-muted);text-align:center;padding:12px;">Settings endpoints not available on this server.</div>';
  });
  fetch('/api/settings/config').then(r=>r.json()).then(config => {
    const container = document.getElementById('settingsKeys');
    if(config.api_keys && config.api_keys.length === 0) container.innerHTML='<div style="font-size:11px;color:var(--text-muted);">No API keys stored.</div>';
    else if(config.api_keys) container.innerHTML = config.api_keys.map(k => `<div class="modal-key-card"><div><div class="modal-key-name">${k.provider}/${k.key_name}</div><div class="modal-key-label">${k.label||'No label'} ${k.is_active?'✅':'❌'}</div></div><button class="btn-secondary" onclick="deleteKey(${k.id})" style="color:#ef4444;font-size:10px;padding:3px 8px;">Remove</button></div>`).join('');
    else container.innerHTML = '<div style="font-size:11px;color:var(--text-muted);">API key management not available.</div>';
    const envHtml = Object.entries(config.env_keys||{}).filter(([,v])=>v).map(([k])=>`<span class="badge-chip accent">${k}</span>`).join(' ');
    if(envHtml) container.innerHTML += `<div style="margin-top:8px;font-size:10px;color:var(--text-muted);">From env: ${envHtml}</div>`;
  }).catch(()=>{
    document.getElementById('settingsKeys').innerHTML = '<div style="font-size:11px;color:var(--text-muted);">API key management not available on this server.</div>';
  });
  fetch('/api/settings/providers').then(r=>r.json()).then(providers => {
    const sel = document.getElementById('keyProvider');
    const keyProviders = providers.filter(p=>p.requires_key);
    fetch('/api/settings/integrations').then(r=>r.json()).then(integrations => {
      sel.innerHTML = '<option value="">Select provider...</option>' + keyProviders.map(p=>`<optgroup label="${p.name}"><option value="${p.id}|${p.key_name}">${p.key_name}</option></optgroup>`).join('') + `<optgroup label="Integrations">${integrations.map(i=>`<option value="${i.id}|${i.key_name}">${i.name}</option>`).join('')}</optgroup>`;
    });
  }).catch(()=>{});
  fetch('/api/settings/integrations').then(r=>r.json()).then(integrations => {
    document.getElementById('settingsIntegrations').innerHTML = integrations.map(i => `<div class="modal-provider-card"><div><div class="modal-provider-name">${i.name}</div><div class="modal-provider-desc">${i.description}</div><div style="font-size:10px;color:var(--accent);margin-top:2px;"><a href="${i.url}" target="_blank">${i.url}</a></div></div><div style="font-size:10px;color:var(--text-muted);">Key: ${i.key_name}</div></div>`).join('');
  }).catch(()=>{
    document.getElementById('settingsIntegrations').innerHTML = '<div style="font-size:11px;color:var(--text-muted);text-align:center;padding:12px;">No integrations configured.</div>';
  });
}

function setDefaultProvider(id) { fetch(`/api/settings/provider/${id}/default`,{method:'POST'}).then(()=>loadSettings()); }
function showAddKeyForm() { const f=document.getElementById('addKeyForm'); f.style.display=f.style.display==='none'?'block':'none'; document.getElementById('keyProvider').onchange=function(){const[_,kn]=this.value.split('|');if(kn)document.getElementById('keyName').value=kn;}; }
function saveKey() {
  const provider=document.getElementById('keyProvider').value.split('|')[0];
  const keyName=document.getElementById('keyName').value;
  const keyValue=document.getElementById('keyValue').value;
  const label=document.getElementById('keyLabel').value;
  if(!keyName||!keyValue) { alert('Fill in key name and value'); return; }
  fetch('/api/settings/api-key',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider,key_name:keyName,key_value:keyValue,label})}).then(r=>r.json()).then(()=>{document.getElementById('keyValue').value='';document.getElementById('keyLabel').value='';loadSettings();});
}
function deleteKey(id) { if(!confirm('Remove this key?')) return; fetch(`/api/settings/api-key/${id}`,
{method:'DELETE'}).then(r=>r.json()).then(()=>loadSettings()); }

document.addEventListener('keydown', e => {
  if(e.key==='Escape') document.getElementById('settingsModal').classList.remove('visible');
});
