/**
 * Heart Guard V1 — Real-Time Dashboard & Simulator Controller
 * Connects via WebSocket / REST to FastAPI backend.
 * Provides live PPG waveform canvas, Chart.js trend visualizer,
 * stateful alert engine updates, and 1-click scenario simulation.
 */

document.addEventListener('DOMContentLoaded', () => {
  const USER_ID = 'user_001';
  const BASE_URL = window.location.origin;
  
  // DOM Elements
  const bpmDisplay = document.getElementById('dash-bpm');
  const tempDisplay = document.getElementById('dash-temp');
  const activityDisplay = document.getElementById('dash-activity');
  const qualityDisplay = document.getElementById('dash-quality');
  
  const baselineMean = document.getElementById('baseline-mean');
  const baselineStd = document.getElementById('baseline-std');
  const baselineExercise = document.getElementById('baseline-exercise');
  const baselineSamples = document.getElementById('baseline-samples');
  const calibrationBadge = document.getElementById('calibration-badge');
  
  const alertBanner = document.getElementById('alert-banner');
  const alertTag = document.getElementById('alert-tier-tag');
  const alertExplanation = document.getElementById('alert-explanation');
  const sosBtnContainer = document.getElementById('sos-btn-container');
  
  const historyTableBody = document.getElementById('history-table-body');
  
  // Modal Elements
  const sosModal = document.getElementById('sos-modal');
  const sosCountdown = document.getElementById('sos-countdown');
  const cancelSosBtn = document.getElementById('btn-cancel-sos');
  const confirmSosBtn = document.getElementById('btn-confirm-sos');
  const triggerSosHeaderBtn = document.getElementById('btn-header-sos');

  let activeStreamInterval = null;
  let chartInstance = null;
  let sosTimer = null;

  // ── 1. Initialize Canvas PPG Waveform Oscilloscope ────────────────────────
  const canvas = document.getElementById('ecg-canvas');
  const ctx = canvas ? canvas.getContext('2d') : null;
  let ecgPoints = [];
  let ecgPhase = 0;
  let currentBPM = 68;
  
  function initCanvas() {
    if (!canvas) return;
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
  }
  window.addEventListener('resize', initCanvas);
  initCanvas();

  function drawECG() {
    if (!ctx || !canvas) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Grid lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
    ctx.lineWidth = 1;
    for (let x = 0; x < canvas.width; x += 30) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvas.height);
      ctx.stroke();
    }
    for (let y = 0; y < canvas.height; y += 30) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
      ctx.stroke();
    }

    // PPG Pulse Wave Math
    const freq = currentBPM / 60.0;
    const speed = 0.04;
    ecgPhase += speed;
    
    ctx.beginPath();
    ctx.strokeStyle = '#00f2fe';
    ctx.lineWidth = 2.5;
    ctx.shadowColor = '#00f2fe';
    ctx.shadowBlur = 10;
    
    const cy = canvas.height / 2;
    for (let x = 0; x < canvas.width; x += 2) {
      const t = x * 0.015 + ecgPhase;
      const pulse = Math.sin(2 * Math.PI * freq * t) + 
                    0.4 * Math.sin(4 * Math.PI * freq * t);
      const y = cy - pulse * (canvas.height * 0.25);
      
      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
    
    requestAnimationFrame(drawECG);
  }
  drawECG();

  // ── 2. Initialize Chart.js Trend Visualizer ───────────────────────────────
  function initChart() {
    const chartCtx = document.getElementById('trend-chart')?.getContext('2d');
    if (!chartCtx) return;

    chartInstance = new Chart(chartCtx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Heart Rate (BPM)',
            data: [],
            borderColor: '#ff2a5f',
            backgroundColor: 'rgba(255, 42, 95, 0.1)',
            borderWidth: 2.5,
            tension: 0.3,
            fill: true,
            pointRadius: 3,
            pointHoverRadius: 6,
          },
          {
            label: 'Resting Baseline Mean',
            data: [],
            borderColor: 'rgba(0, 245, 160, 0.6)',
            borderWidth: 1.5,
            borderDash: [6, 4],
            pointRadius: 0,
            fill: false,
          },
          {
            label: 'Temperature (°C)',
            data: [],
            borderColor: '#00f2fe',
            borderWidth: 1.5,
            yAxisID: 'yTemp',
            pointRadius: 2,
            fill: false,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            labels: { color: '#94a3b8', font: { family: 'Plus Jakarta Sans', size: 11 } }
          },
          tooltip: {
            backgroundColor: 'rgba(15, 21, 41, 0.9)',
            titleColor: '#ffffff',
            bodyColor: '#cbd5e1',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
          }
        },
        scales: {
          x: {
            ticks: { color: '#64748b', font: { size: 10 } },
            grid: { color: 'rgba(255, 255, 255, 0.04)' }
          },
          y: {
            title: { display: true, text: 'BPM', color: '#ff2a5f', font: { size: 11 } },
            ticks: { color: '#64748b' },
            grid: { color: 'rgba(255, 255, 255, 0.04)' },
            suggestedMin: 50,
            suggestedMax: 140,
          },
          yTemp: {
            position: 'right',
            title: { display: true, text: 'Temp °C', color: '#00f2fe', font: { size: 11 } },
            ticks: { color: '#64748b' },
            grid: { drawOnChartArea: false },
            suggestedMin: 35.0,
            suggestedMax: 40.0,
          }
        }
      }
    });
  }
  initChart();

  function updateChart(hr, temp, timestamp, baselineHr = 68.0) {
    if (!chartInstance) return;
    const timeLabel = new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    chartInstance.data.labels.push(timeLabel);
    chartInstance.data.datasets[0].data.push(hr);
    chartInstance.data.datasets[1].data.push(baselineHr);
    chartInstance.data.datasets[2].data.push(temp);

    // Keep max 25 points
    if (chartInstance.data.labels.length > 25) {
      chartInstance.data.labels.shift();
      chartInstance.data.datasets[0].data.shift();
      chartInstance.data.datasets[1].data.shift();
      chartInstance.data.datasets[2].data.shift();
    }

    chartInstance.update('none');
  }

  // ── 3. Baseline & Status Data Fetchers ────────────────────────────────────
  async function fetchBaseline() {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/baseline/${USER_ID}`);
      const data = await res.json();
      
      if (data.baseline_established) {
        baselineMean.textContent = `${Math.round(data.resting_hr.mean)} BPM`;
        baselineStd.textContent = `±${data.resting_hr.std_dev.toFixed(1)} BPM`;
        baselineExercise.textContent = data.exercise_hr ? `${Math.round(data.exercise_hr.mean)} BPM` : '--';
        baselineSamples.textContent = `${data.sample_count} samples`;
        
        calibrationBadge.textContent = 'ESTABLISHED';
        calibrationBadge.className = 'status-pill';
        calibrationBadge.style.borderColor = 'var(--emerald)';
        calibrationBadge.style.color = 'var(--emerald)';
      } else {
        calibrationBadge.textContent = `CALIBRATING (${data.sample_count || 0}/100)`;
        calibrationBadge.className = 'status-pill';
        calibrationBadge.style.borderColor = 'var(--amber)';
        calibrationBadge.style.color = 'var(--amber)';
      }
    } catch (e) {
      console.error('Error fetching baseline:', e);
    }
  }

  async function fetchHistory() {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/history/${USER_ID}?limit=10`);
      const data = await res.json();
      renderHistoryTable(data.alerts || []);
    } catch (e) {
      console.error('Error fetching history:', e);
    }
  }

  function renderHistoryTable(alerts) {
    if (!historyTableBody) return;
    if (alerts.length === 0) {
      historyTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 20px;">No alerts triggered yet. System monitoring normally.</td></tr>`;
      return;
    }

    historyTableBody.innerHTML = alerts.map(a => {
      const timeStr = new Date(a.timestamp).toLocaleTimeString();
      const statusFormatted = a.status.replace('_', ' ').toUpperCase();
      const hrVal = a.current_readings?.heart_rate_bpm ? `${Math.round(a.current_readings.heart_rate_bpm)} BPM` : '--';
      
      return `
        <tr style="border-bottom: 1px solid var(--border-glass);">
          <td style="padding: 12px; font-family: var(--font-mono); font-size: 0.85rem;">${timeStr}</td>
          <td style="padding: 12px;"><span class="tier-tag tier-${a.status}">${statusFormatted}</span></td>
          <td style="padding: 12px; font-family: var(--font-mono); font-weight: 700;">${hrVal}</td>
          <td style="padding: 12px; font-size: 0.85rem; color: var(--text-muted);">${a.explanation}</td>
          <td style="padding: 12px; font-weight: 700; color: var(--cyan);">${a.pattern?.severity_score || 0}/5</td>
        </tr>
      `;
    }).join('');
  }

  // ── 4. Update UI with Alert Engine Output ────────────────────────────────
  function handleAlertUpdate(alert) {
    if (!alert) return;
    
    // Update live metrics ribbon
    const readings = alert.current_readings || {};
    if (readings.heart_rate_bpm) {
      currentBPM = Math.round(readings.heart_rate_bpm);
      bpmDisplay.textContent = currentBPM;
    } else {
      bpmDisplay.textContent = '--';
    }

    if (readings.temperature_celsius) {
      tempDisplay.textContent = readings.temperature_celsius.toFixed(1);
    }
    
    if (readings.activity_state) {
      const stateStr = readings.activity_state.replace('_', ' ').toUpperCase();
      activityDisplay.textContent = stateStr;
    }

    // Update signal quality badge
    const quality = alert.signal_quality || 'good';
    qualityDisplay.textContent = quality.toUpperCase();
    qualityDisplay.className = `metric-badge badge-${quality}`;

    // Update Alert Banner
    const status = alert.status || 'normal';
    alertBanner.className = `alert-banner-card status-${status}`;
    alertTag.className = `alert-tier-tag tier-${status}`;
    alertTag.textContent = status.replace('_', ' ').toUpperCase();
    alertExplanation.textContent = alert.explanation || 'Readings are within normal baseline range.';

    // Update SOS button visibility
    if (alert.sos_available || status === 'sos') {
      sosBtnContainer.style.display = 'block';
    } else {
      sosBtnContainer.style.display = 'none';
    }

    // Append point to Chart.js
    if (readings.heart_rate_bpm && readings.temperature_celsius) {
      updateChart(readings.heart_rate_bpm, readings.temperature_celsius, alert.timestamp || new Date().toISOString());
    }

    // Refresh history
    fetchHistory();
    fetchBaseline();
  }

  // ── 5. WebSocket Connection ──────────────────────────────────────────────
  function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/dashboard/${USER_ID}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[ws] Connected to Heart Guard dashboard stream.');
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'alert_update') {
        handleAlertUpdate(msg.payload);
      }
    };

    ws.onclose = () => {
      console.log('[ws] Connection closed. Reconnecting in 3s...');
      setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (err) => {
      console.error('[ws] Error:', err);
      ws.close();
    };
  }
  connectWebSocket();

  // Initial fetch
  fetchBaseline();
  fetchHistory();

  // ── 6. Synthetic Payload Simulator Engine ────────────────────────────────
  function generateSyntheticPayload(scenarioKey) {
    const scenarios = {
      normal_resting: { hr: 68, state: 'resting', temp: 36.7, noise: 0.03 },
      elevated_resting: { hr: 112, state: 'resting', temp: 37.4, noise: 0.04 },
      exercise_normal: { hr: 130, state: 'exercise', temp: 36.9, noise: 0.05 },
      noisy_signal: { hr: 155, state: 'resting', temp: 36.6, noise: 3.0 },
      extreme_spike: { hr: 180, state: 'resting', temp: 37.8, noise: 0.03 }
    };

    const s = scenarios[scenarioKey] || scenarios.normal_resting;
    
    // Generate PPG signal
    const raw_signal = [];
    const freq = s.hr / 60.0;
    for (let i = 0; i < 500; i++) {
      const ti = i / 100.0;
      let val = Math.sin(2 * Math.PI * freq * ti) + 0.5 * Math.sin(4 * Math.PI * freq * ti);
      if (s.noise > 1.0 && Math.random() < 0.25) {
        val += (Math.random() > 0.5 ? 15 : -15);
      }
      raw_signal.push(val);
    }

    const accelMap = {
      resting: { x: 0.1, y: 9.7, z: 0.2 },
      light_activity: { x: 0.8, y: 9.8, z: 1.1 },
      exercise: { x: 3.5, y: 10.5, z: 4.2 }
    };

    return {
      user_id: USER_ID,
      device_id: 'dev_simulator',
      timestamp: new Date().toISOString(),
      sensor: {
        ppg: { raw_signal, sampling_rate_hz: 100 },
        accelerometer: accelMap[s.state] || accelMap.resting,
        temperature: { value_celsius: s.temp }
      }
    };
  }

  async function sendSingleIngest(scenarioKey) {
    const payload = generateSyntheticPayload(scenarioKey);
    try {
      const res = await fetch(`${BASE_URL}/api/v1/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      console.log('[ingest result]', data);
    } catch (e) {
      console.error('Ingest failed:', e);
    }
  }

  function startStream(scenarioKey, count = 10, intervalMs = 1500) {
    if (activeStreamInterval) clearInterval(activeStreamInterval);
    let sent = 0;
    
    // Highlight active button
    document.querySelectorAll('.sim-btn').forEach(btn => btn.classList.remove('active'));
    const targetBtn = document.getElementById(`sim-${scenarioKey}`);
    if (targetBtn) targetBtn.classList.add('active');

    sendSingleIngest(scenarioKey);
    sent++;

    activeStreamInterval = setInterval(() => {
      if (sent >= count) {
        clearInterval(activeStreamInterval);
        activeStreamInterval = null;
        if (targetBtn) targetBtn.classList.remove('active');
        return;
      }
      sendSingleIngest(scenarioKey);
      sent++;
    }, intervalMs);
  }

  // Simulator Button Listeners
  document.getElementById('sim-normal')?.addEventListener('click', () => startStream('normal_resting', 5));
  document.getElementById('sim-elevated')?.addEventListener('click', () => startStream('elevated_resting', 10));
  document.getElementById('sim-exercise')?.addEventListener('click', () => startStream('exercise_normal', 5));
  document.getElementById('sim-noisy')?.addEventListener('click', () => startStream('noisy_signal', 3));
  document.getElementById('sim-extreme')?.addEventListener('click', () => startStream('extreme_spike', 3));
  
  document.getElementById('sim-seed')?.addEventListener('click', async () => {
    const seedBtn = document.getElementById('sim-seed');
    seedBtn.disabled = true;
    seedBtn.textContent = 'Seeding (100)...';
    
    for (let i = 0; i < 30; i++) {
      await sendSingleIngest('normal_resting');
    }
    await fetch(`${BASE_URL}/api/v1/admin/recompute_baseline/${USER_ID}`, { method: 'POST' });
    fetchBaseline();
    
    seedBtn.disabled = false;
    seedBtn.innerHTML = '<span class="sim-icon">⚡</span> Seed 100 Baseline';
  });

  // ── 7. Emergency SOS Modal Controller ────────────────────────────────────
  function openSosModal() {
    sosModal.classList.add('active');
    let seconds = 5;
    sosCountdown.textContent = seconds;

    if (sosTimer) clearInterval(sosTimer);
    sosTimer = setInterval(() => {
      seconds--;
      sosCountdown.textContent = seconds;
      if (seconds <= 0) {
        clearInterval(sosTimer);
        sosCountdown.textContent = 'DISPATCHED';
        alert('🚨 EMERGENCY SOS DISPATCHED TO LOCAL RESPONDERS AND EMERGENCY CONTACTS.');
      }
    }, 1000);
  }

  function closeSosModal() {
    sosModal.classList.remove('active');
    if (sosTimer) clearInterval(sosTimer);
  }

  triggerSosHeaderBtn?.addEventListener('click', openSosModal);
  document.getElementById('btn-banner-sos')?.addEventListener('click', openSosModal);
  cancelSosBtn?.addEventListener('click', closeSosModal);
  confirmSosBtn?.addEventListener('click', () => {
    if (sosTimer) clearInterval(sosTimer);
    sosCountdown.textContent = 'DISPATCHED';
    alert('🚨 EMERGENCY SOS DISPATCHED IMMEDIATELY.');
  });

});
