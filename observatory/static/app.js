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
  document.querySelector('.policy-note b').textContent = `${(run.gate.policy.max_quality_drop * 100).toFixed(1)}%`;
  $('export-json').href = `/api/runs/${run.id}/export?format=json`;
  $('export-csv').href = `/api/runs/${run.id}/export?format=csv`;
  $('comparison-result').textContent = 'Choose an earlier experiment to inspect case-level changes.';
  $('comparison-cases').replaceChildren();
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
  const previousSelection = $('compare-baseline').value;
  $('compare-baseline').replaceChildren(...history.map(run => {
    const option = element('option', `${run.dataset} · ${run.scenario} · ${run.id.slice(0, 8)}`);
    option.value = run.id;
    return option;
  }));
  if (history.some(run => run.id === previousSelection)) $('compare-baseline').value = previousSelection;
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
      body: JSON.stringify({scenario: $('scenario').value, dataset_id: $('dataset').value || null,
        max_quality_drop: Number($('quality-budget').value), max_latency_ratio: Number($('latency-budget').value)})});
    history = await request('/api/runs');
    renderRun(run);
  } catch (error) { showError(error.message); }
  finally { $('run-button').disabled = false; $('run-button').textContent = '＋ Run evaluation'; }
});
$('failed-only').addEventListener('change', renderTraces);
$('close-dialog').addEventListener('click', () => $('trace-dialog').close());

async function loadDatasets(selected) {
  const datasets = await request('/api/datasets');
  $('dataset').replaceChildren(...datasets.map(dataset => {
    const option = element('option', `${dataset.name} · ${dataset.cases} cases`);
    option.value = dataset.id || '';
    return option;
  }));
  if (selected) $('dataset').value = selected;
}

$('upload-dataset').addEventListener('click', async () => {
  const file = $('dataset-file').files[0];
  if (!file || file.size > 512000) { showError('Choose a JSONL file no larger than 512 KB.'); return; }
  $('upload-dataset').disabled = true;
  $('error').hidden = true;
  try {
    const dataset = await request('/api/datasets', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: $('dataset-name').value, jsonl: await file.text()})});
    await loadDatasets(dataset.id);
    $('dataset-status').textContent = `${dataset.name} · ${dataset.cases} cases · SHA-256 ${dataset.id}`;
  } catch (error) { showError('Dataset could not be uploaded. Check its JSONL fields and contracts in the API reference.'); }
  finally { $('upload-dataset').disabled = false; }
});

$('compare-button').addEventListener('click', async () => {
  if (!currentRun || !$('compare-baseline').value) { showError('Run an evaluation first.'); return; }
  $('compare-button').disabled = true;
  $('error').hidden = true;
  try {
    const params = new URLSearchParams({baseline: $('compare-baseline').value, candidate: currentRun.id});
    const report = await request(`/api/compare?${params}`);
    const interval = values => values.map(value => `${(value * 100).toFixed(1)}%`).join(' – ');
    $('comparison-result').textContent = `${report.regressions} regressions · ${report.improvements} improvements · ${(report.pass_rate_delta * 100).toFixed(1)} pp change. Case-proportion Wilson 95% intervals: earlier ${interval(report.baseline_wilson_95)}, selected ${interval(report.candidate_wilson_95)}. ${report.limitations}`;
    $('comparison-cases').replaceChildren(...report.cases_detail.map(item => {
      const row = element('tr');
      row.append(element('td', item.case_id), element('td', item.category), element('td', item.transition.replaceAll('_', ' ')));
      return row;
    }));
  } catch (error) { showError('Comparison requires two existing runs with identical dataset fingerprints.'); }
  finally { $('compare-button').disabled = false; }
});
async function initialize() {
  try {
    await loadDatasets();
    history = await request('/api/runs');
    renderHistory();
    if (history.length) renderRun(await request(`/api/runs/${history[0].id}`));
  } catch (error) { showError('The workspace could not connect to the API. Check the server and refresh.'); }
}
initialize();
