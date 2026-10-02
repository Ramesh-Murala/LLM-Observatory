const $ = (id) => document.getElementById(id);
let currentRun = null;
let history = [];

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`Request failed (${response.status}). Please try again.`);
  return response.json();
}

function badge(passed, passText = 'Passed', failText = 'Failed') {
  return element('span', passed ? passText : failText, `badge${passed ? '' : ' fail'}`);
}

function renderRun(run) {
  currentRun = run;
  const base = run.summaries.baseline;
  const candidate = run.summaries.candidate;
  document.querySelector('.notice div').textContent = run.provider === 'fixture'
    ? 'Local demo environment · deterministic responses · simulated latency · estimated token usage · no paid calls'
    : 'Remote provider evidence · measured latency · cost estimates depend on supplied pricing';
  document.querySelector('.notice-tag').textContent = `${candidate.cases} CASES`;
  document.querySelector('.table-tag').textContent = run.dataset;
  $('quality').textContent = `${(candidate.pass_rate * 100).toFixed(1)}%`;
  $('quality-note').textContent = `${((candidate.pass_rate - base.pass_rate) * 100).toFixed(1)} pp vs baseline`;
  $('latency').textContent = `${candidate.p95_ms.toFixed(0)} ms`;
  $('tokens').textContent = candidate.tokens.toLocaleString();
  const tokenNote = document.querySelector('.stat:nth-child(3) small');
  tokenNote.textContent = run.provider === 'fixture' ? 'Word estimates · $0 provider cost'
    : candidate.estimated_cost_usd == null ? 'Provider usage · cost not configured'
    : `Estimated cost $${candidate.estimated_cost_usd.toFixed(5)}`;
  document.querySelector('.stat:nth-child(2) small').textContent = run.provider === 'fixture'
    ? 'Simulated in fixture mode' : 'Measured provider response time';
  const path = document.querySelector('.spark path');
  const candidateTraces = run.traces.filter(trace => trace.variant === 'candidate');
  const maxLatency = Math.max(...candidateTraces.map(trace => trace.latency_ms), 1);
  path.setAttribute('d', candidateTraces.map((trace, index) =>
    `${index === 0 ? 'M' : 'L'}${index * 250 / Math.max(candidateTraces.length - 1, 1)} ${30 - trace.latency_ms / maxLatency * 28}`).join(' '));
  $('decision').textContent = run.gate.passed ? 'Approved' : 'Blocked';
  $('decision').style.color = run.gate.passed ? 'var(--mint)' : 'var(--red)';
  $('decision-note').textContent = run.gate.passed ? 'All release checks passed' : `${run.gate.reasons.length} release check failed`;
  $('gate-verdict').textContent = run.gate.passed ? 'Ready for the next step.' : 'Regression detected.';
  $('gate-description').textContent = run.gate.passed
    ? 'The candidate stays within the configured budgets. All cases completed without provider errors.'
    : 'The candidate exceeds a release budget. Inspect the failing cases before shipping this change.';
  $('gate-reasons').replaceChildren(...run.gate.reasons.map(reason => element('li', reason)));
  const categories = [...new Set(run.traces.map(trace => trace.category))];
  $('categories').replaceChildren(...categories.map(category => {
    const row = element('div', undefined, 'category');
    row.append(element('span', category, 'category-name'));
    const bars = element('div');
    let candidateRate = 0;
    for (const variant of ['baseline', 'candidate']) {
      const traces = run.traces.filter(trace => trace.category === category && trace.variant === variant);
      const rate = traces.filter(trace => trace.passed).length / traces.length;
      const track = element('div', undefined, `bar-track ${variant}`);
      const fill = element('span');
      fill.style.width = `${rate * 100}%`;
      track.append(fill);
      bars.append(track);
      if (variant === 'candidate') candidateRate = rate;
    }
    row.append(bars, element('span', `${(candidateRate * 100).toFixed(0)}%`, 'bar-label'));
    return row;
  }));
  renderTraces();
  renderHistory();
}

function showTrace(trace) {
  $('trace-title').textContent = trace.case_id;
  $('trace-meta').textContent = `${trace.variant} · ${trace.category} · trace ${trace.trace_id} · ${trace.latency_source} latency`;
  $('trace-meta').textContent += ` · span ${trace.span_id || 'legacy'}`;
  $('trace-prompt').textContent = trace.prompt;
  $('trace-output').textContent = trace.error ? `Provider error: ${trace.error}` : trace.output;
  $('trace-checks').replaceChildren(...trace.checks.map(check => {
    const row = element('div', undefined, 'check-row');
    row.append(badge(check.passed), element('span', `${check.name}: ${check.reason}`));
    return row;
  }));
  $('trace-dialog').showModal();
}

function renderTraces() {
  if (!currentRun) return;
  const traces = currentRun.traces.filter(trace => !$('failed-only').checked || !trace.passed);
  $('traces-body').replaceChildren(...traces.map(trace => {
    const row = element('tr');
    const cell = element('td');
    const button = element('button', trace.case_id, 'row-button');
    button.append(element('small', trace.span_id || trace.id.slice(0, 16)));
    button.addEventListener('click', () => showTrace(trace));
    cell.append(button);
    row.append(cell, element('td', trace.category), element('td', trace.variant),
      element('td', `${trace.latency_ms.toFixed(0)} ms`));
    const result = element('td'); result.append(badge(trace.passed)); row.append(result);
    return row;
  }));
  if (!traces.length) {
    const row = element('tr'); const cell = element('td', 'No cases match this filter.', 'empty');
    cell.colSpan = 5; row.append(cell); $('traces-body').append(row);
  }
}

function renderHistory() {
  $('run-count').textContent = history.length;
  $('runs-body').replaceChildren(...history.map(run => {
    const row = element('tr', undefined, run.id === currentRun?.id ? 'selected-row' : '');
    const cell = element('td');
    const button = element('button', `eval-${run.id.slice(0, 8)}`, 'row-button');
    button.append(element('small', `SHA ${run.dataset_sha256.slice(0, 12)}`));
    button.addEventListener('click', async () => {
      try { renderRun(await request(`/api/runs/${run.id}`)); }
      catch (error) { showError(error.message); }
    });
    cell.append(button);
    row.append(cell, element('td', run.scenario),
      element('td', `${(run.summaries.candidate.pass_rate * 100).toFixed(1)}%`),
      element('td', `${run.summaries.candidate.p95_ms.toFixed(0)} ms`));
    const gate = element('td'); gate.append(badge(run.gate.passed, 'Approved', 'Blocked'));
    row.append(gate, element('td', new Date(run.created_at).toLocaleString(undefined, {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})));
    return row;
  }));
}

function showError(message) { $('error').hidden = false; $('error').textContent = message; }

$('run-button').addEventListener('click', async () => {
  $('run-button').disabled = true;
  $('run-button').textContent = 'Evaluating…';
  $('error').hidden = true;
  try {
    const run = await request('/api/runs', {method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({scenario: $('scenario').value})});
    history = await request('/api/runs');
    renderRun(run);
  } catch (error) { showError(error.message); }
  finally { $('run-button').disabled = false; $('run-button').textContent = '＋ Run evaluation'; }
});
$('failed-only').addEventListener('change', renderTraces);
$('close-dialog').addEventListener('click', () => $('trace-dialog').close());
async function initialize() {
  try {
    history = await request('/api/runs');
    renderHistory();
    if (history.length) renderRun(await request(`/api/runs/${history[0].id}`));
  } catch (error) { showError('The workspace could not connect to the API. Check the server and refresh.'); }
}
initialize();
