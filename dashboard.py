#!/usr/bin/env python3
"""
AGY Memory Engine - Real-Time Debug Dashboard
Zero-dependency, standalone live web interface for inspecting and testing
multi-layer memories, knowledge graph relations, and turn queue state.
"""

import os
import sys
import json
import time
import sqlite3
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import (
    DB_PATH,
    QUEUE_DB_PATH,
    MODEL_NAME,
    DASHBOARD_PORT,
    DASHBOARD_HOST,
    INACTIVITY_THRESHOLD_SECONDS,
    MAX_WAIT_THRESHOLD_SECONDS,
    DEFAULT_TELEGRAM_CHAT_ID
)
from schema import db_session
from agy_memory import extract_multilingual_tokens, get_all_vocabulary
from queue_manager import get_pending_stats, get_pending_turns


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AGY Memory Engine • Live Debug Dashboard</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🧠</text></svg>">
  <link rel="apple-touch-icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🧠</text></svg>">
  <meta name="apple-mobile-web-app-title" content="AGY Memory">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="theme-color" content="#0d1117">
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --card-border: #30363d;
      --text: #c9d1d9;
      --text-bright: #f0f6fc;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --accent-glow: rgba(88, 166, 255, 0.15);
      --success: #3fb950;
      --warning: #d29922;
      --danger: #f85149;
      --purple: #bc8cff;
      --cyan: #39c5cf;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 20px;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 15px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 20px;
    }
    .header-title {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .header-title h1 {
      font-size: 1.4rem;
      color: var(--text-bright);
      font-weight: 600;
    }
    .pulse-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      background: rgba(63, 185, 80, 0.15);
      border: 1px solid rgba(63, 185, 80, 0.4);
      color: var(--success);
      font-size: 0.75rem;
      border-radius: 20px;
      font-weight: 500;
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      background: var(--success);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--success);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.8); }
      100% { opacity: 1; transform: scale(1); }
    }
    .header-meta {
      display: flex;
      gap: 10px;
      align-items: center;
      font-size: 0.85rem;
    }
    .badge {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      padding: 4px 10px;
      border-radius: 6px;
      color: var(--text-muted);
      font-family: monospace;
    }
    .badge b { color: var(--accent); }

    /* Top Stats Grid */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 15px;
      margin-bottom: 25px;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 15px;
      position: relative;
      overflow: hidden;
    }
    .stat-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      background: var(--accent);
    }
    .stat-card.c-facts::before { background: var(--accent); }
    .stat-card.c-episodes::before { background: var(--purple); }
    .stat-card.c-learnings::before { background: var(--cyan); }
    .stat-card.c-links::before { background: var(--success); }
    .stat-card.c-queue::before { background: var(--warning); }

    .stat-label {
      font-size: 0.8rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 5px;
    }
    .stat-val {
      font-size: 1.8rem;
      font-weight: 700;
      color: var(--text-bright);
    }
    .stat-sub {
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-top: 4px;
    }

    /* Tabs */
    .tabs {
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 20px;
      overflow-x: auto;
    }
    .tab-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      padding: 10px 16px;
      font-size: 0.9rem;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .tab-btn:hover { color: var(--text-bright); }
    .tab-btn.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
    }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* Search Sandbox */
    .search-box {
      display: flex;
      gap: 10px;
      margin-bottom: 20px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      padding: 8px 12px;
      border-radius: 8px;
    }
    .search-box input {
      flex: 1;
      background: none;
      border: none;
      color: var(--text-bright);
      font-size: 1rem;
      outline: none;
    }
    .search-meta {
      display: flex;
      align-items: center;
      font-size: 0.8rem;
      color: var(--text-muted);
      font-family: monospace;
    }

    /* Cards & Lists */
    .item-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 15px;
      margin-bottom: 12px;
      transition: border-color 0.2s;
    }
    .item-card:hover { border-color: #58a6ff66; }
    .item-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .item-id {
      font-family: monospace;
      font-weight: 600;
      color: var(--accent);
      font-size: 0.9rem;
    }
    .pill {
      font-size: 0.75rem;
      padding: 2px 8px;
      border-radius: 12px;
      font-weight: 500;
      border: 1px solid var(--card-border);
    }
    .pill.active { background: rgba(63, 185, 80, 0.15); color: var(--success); border-color: rgba(63, 185, 80, 0.4); }
    .pill.cooling { background: rgba(210, 153, 34, 0.15); color: var(--warning); border-color: rgba(210, 153, 34, 0.4); }
    .pill.historic { background: rgba(139, 148, 158, 0.15); color: var(--text-muted); border-color: rgba(139, 148, 158, 0.4); }
    .pill.resolved { background: rgba(57, 197, 207, 0.15); color: var(--cyan); border-color: rgba(57, 197, 207, 0.4); }
    .pill.category { background: rgba(88, 166, 255, 0.1); color: var(--accent); }

    .item-body {
      color: var(--text-bright);
      font-size: 0.95rem;
      margin-bottom: 8px;
      white-space: pre-wrap;
    }
    .item-meta {
      font-size: 0.8rem;
      color: var(--text-muted);
      display: flex;
      gap: 15px;
      flex-wrap: wrap;
    }
    .item-meta span b { color: var(--text); }

    /* Graph Visualizer */
    .graph-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 15px;
    }
    .graph-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 15px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .graph-node {
      font-family: monospace;
      font-size: 0.85rem;
      color: var(--text-bright);
      background: rgba(255,255,255,0.05);
      padding: 6px 10px;
      border-radius: 6px;
      border: 1px solid var(--card-border);
      flex: 1;
      text-align: center;
      word-break: break-all;
    }
    .graph-arrow {
      color: var(--success);
      font-size: 0.8rem;
      font-weight: bold;
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
    }
    .graph-relation {
      font-size: 0.7rem;
      color: var(--text-muted);
      text-transform: uppercase;
      font-family: monospace;
    }

    /* Queue & Debounce */
    .queue-bar-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 15px;
      margin-bottom: 20px;
    }
    .queue-bar-header {
      display: flex;
      justify-content: space-between;
      margin-bottom: 8px;
      font-size: 0.85rem;
    }
    .progress-track {
      height: 8px;
      background: rgba(255,255,255,0.1);
      border-radius: 4px;
      overflow: hidden;
      margin-bottom: 10px;
    }
    .progress-fill {
      height: 100%;
      background: var(--warning);
      width: 0%;
      transition: width 0.5s ease;
    }
    .btn {
      background: var(--accent);
      color: #0d1117;
      border: none;
      padding: 6px 14px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 0.85rem;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    .btn:hover { opacity: 0.9; }
    .btn-secondary {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-bright);
    }
  </style>
</head>
<body>

  <header>
    <div class="header-title">
      <h1>🧠 AGY Memory Engine</h1>
      <div class="pulse-badge"><div class="pulse-dot"></div> Live FTS5</div>
    </div>
    <div class="header-meta">
      <div class="badge">Model: <b id="lbl-model">-</b></div>
      <div class="badge">DB: <b id="lbl-db-size">-</b></div>
      <button class="btn btn-secondary" onclick="fetchData()">🔄 Refresh</button>
      <button class="btn" onclick="forceWorker()">⚡ Force Queue</button>
    </div>
  </header>

  <!-- Top Stats Grid -->
  <div class="stats-grid">
    <div class="stat-card c-facts">
      <div class="stat-label">Layer 1: Facts</div>
      <div class="stat-val" id="cnt-facts">0</div>
      <div class="stat-sub">Atomic Master Data & Specs</div>
    </div>
    <div class="stat-card c-episodes">
      <div class="stat-label">Layer 2: Episodes</div>
      <div class="stat-val" id="cnt-episodes">0</div>
      <div class="stat-sub">Narratives & Topic Dossiers</div>
    </div>
    <div class="stat-card c-learnings">
      <div class="stat-label">Layer 3: Learnings</div>
      <div class="stat-val" id="cnt-learnings">0</div>
      <div class="stat-sub">Heuristics & Rules of Thumb</div>
    </div>
    <div class="stat-card c-links">
      <div class="stat-label">Layer 4: Relations</div>
      <div class="stat-val" id="cnt-links">0</div>
      <div class="stat-sub">Knowledge Graph Entity Links</div>
    </div>
    <div class="stat-card c-queue">
      <div class="stat-label">Turn Queue</div>
      <div class="stat-val" id="cnt-queue">0</div>
      <div class="stat-sub" id="lbl-queue-sub">0 pending</div>
    </div>
  </div>

  <!-- Tabs Navigation -->
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('search')">🔍 Live Search Sandbox</button>
    <button class="tab-btn" onclick="switchTab('queue')">⚡ Turn Queue & Debounce</button>
    <button class="tab-btn" onclick="switchTab('facts')">🧱 Facts (<span id="tab-cnt-facts">0</span>)</button>
    <button class="tab-btn" onclick="switchTab('episodes')">📖 Episodes (<span id="tab-cnt-episodes">0</span>)</button>
    <button class="tab-btn" onclick="switchTab('learnings')">💡 Learnings (<span id="tab-cnt-learnings">0</span>)</button>
    <button class="tab-btn" onclick="switchTab('graph')">🕸️ Entity Graph (<span id="tab-cnt-graph">0</span>)</button>
    <button class="tab-btn" onclick="switchTab('audit')">📜 Audit Log</button>
  </div>

  <!-- TAB 1: Search Sandbox -->
  <div id="tab-search" class="tab-content active">
    <div class="search-box">
      <input type="text" id="inp-search" placeholder="Enter search query (e.g. dog insurance, Tesla, Beelink, Madrid, retirement)..." oninput="debounceSearch()">
      <div class="search-meta" id="search-latency">0 ms</div>
    </div>
    <div id="search-results">
      <p style="color:var(--text-muted); text-align:center; padding: 40px;">Type a search query to test hybrid multilingual FTS5 retrieval in real time.</p>
    </div>
  </div>

  <!-- TAB 2: Queue Monitor -->
  <div id="tab-queue" class="tab-content">
    <div class="queue-bar-container">
      <div class="queue-bar-header">
        <span><b>Calm-Memory Debounce Status</b></span>
        <span id="lbl-debounce-text">Queue is empty</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" id="progress-debounce"></div>
      </div>
      <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.8rem; color:var(--text-muted);">
        <span>Debounce window: 300s (5m idle) / Max timeout: 900s (15m)</span>
        <button class="btn" style="padding: 4px 10px; font-size: 0.75rem;" onclick="forceWorker()">Process Batch Now</button>
      </div>
    </div>
    <h3 style="margin-bottom:15px; font-size:1.1rem; color:var(--text-bright);">Pending Turns in Queue</h3>
    <div id="queue-items"></div>
  </div>

  <!-- TAB 3: Facts -->
  <div id="tab-facts" class="tab-content">
    <div id="facts-items"></div>
  </div>

  <!-- TAB 4: Episodes -->
  <div id="tab-episodes" class="tab-content">
    <div id="episodes-items"></div>
  </div>

  <!-- TAB 5: Learnings -->
  <div id="tab-learnings" class="tab-content">
    <div id="learnings-items"></div>
  </div>

  <!-- TAB 6: Graph -->
  <div id="tab-graph" class="tab-content">
    <div class="graph-grid" id="graph-items"></div>
  </div>

  <!-- TAB 7: Audit Log -->
  <div id="tab-audit" class="tab-content">
    <div id="audit-items"></div>
  </div>

  <script>
    let rawData = null;
    let searchTimer = null;

    function switchTab(name) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.currentTarget.classList.add('active');
      document.getElementById('tab-' + name).classList.add('active');
    }

    async function fetchData() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        rawData = data;

        document.getElementById('lbl-model').innerText = data.model || 'gemini-3.7-flash-high';
        document.getElementById('lbl-db-size').innerText = data.db_size || '-';
        document.getElementById('cnt-facts').innerText = data.counts.facts || 0;
        document.getElementById('cnt-episodes').innerText = data.counts.episodes || 0;
        const qCnt = data.counts.queue_pending || 0;
        document.getElementById('cnt-queue').innerText = qCnt;
        document.getElementById('lbl-queue-sub').innerText = qCnt === 0 ? '0 pending (idle)' : `${qCnt} waiting for debounce`;

        document.getElementById('tab-cnt-facts').innerText = data.counts.facts || 0;
        document.getElementById('tab-cnt-episodes').innerText = data.counts.episodes || 0;
        document.getElementById('tab-cnt-learnings').innerText = data.counts.learnings || 0;
        document.getElementById('tab-cnt-graph').innerText = data.counts.links || 0;

        renderQueue(data.queue);
        renderFacts(data.facts);
        renderEpisodes(data.episodes);
        renderLearnings(data.learnings);
        renderGraph(data.links);
        renderAudit(data.audit);
      } catch (e) {
        console.error("Failed to load dashboard data", e);
      }
    }

    function renderQueue(queue) {
      const qCont = document.getElementById('queue-items');
      const debLbl = document.getElementById('lbl-debounce-text');
      const prog = document.getElementById('progress-debounce');

      if (!queue || queue.pending_count === 0) {
        debLbl.innerText = 'Queue is empty (0 pending turns)';
        prog.style.width = '0%';
        qCont.innerHTML = '<p style="color:var(--text-muted); padding:20px; text-align:center;">No pending turns.</p>';
        return;
      }

      const idleSec = queue.newest_age_seconds || 0;
      const pct = Math.min(100, Math.round((idleSec / 300) * 100));
      prog.style.width = pct + '%';
      debLbl.innerText = `Last message ${idleSec}s ago (batch triggers at 300s idle or 15m timeout)`;

      qCont.innerHTML = queue.turns.map(t => `
        <div class="item-card">
          <div class="item-header">
            <span class="item-id">Turn #${t.id} [${t.source || 'telegram'}]</span>
            <span class="pill active">${t.created_at}</span>
          </div>
          <div class="item-body"><b>User:</b> ${escapeHtml(t.user_prompt)}</div>
          <div class="item-meta">
            <span><b>Status:</b> ${t.status}</span>
            <span><b>Chat ID:</b> ${t.chat_id || '-'}</span>
          </div>
        </div>
      `).join('');
    }

    function renderFacts(facts) {
      const cont = document.getElementById('facts-items');
      if (!facts || facts.length === 0) {
        cont.innerHTML = '<p style="color:var(--text-muted); padding:20px; text-align:center;">No facts stored.</p>';
        return;
      }
      cont.innerHTML = facts.map(f => `
        <div class="item-card">
          <div class="item-header">
            <span class="item-id">${f.id}</span>
            <span class="pill category">${f.category}</span>
          </div>
          <div class="item-body">${escapeHtml(f.fact)}</div>
          <div class="item-meta">
            <span><b>Keywords:</b> ${escapeHtml(f.keywords || '-')}</span>
            <span><b>Updated:</b> ${f.updated_at}</span>
          </div>
        </div>
      `).join('');
    }

    function renderEpisodes(episodes) {
      const cont = document.getElementById('episodes-items');
      if (!episodes || episodes.length === 0) {
        cont.innerHTML = '<p style="color:var(--text-muted); padding:20px; text-align:center;">No episodes stored.</p>';
        return;
      }
      cont.innerHTML = episodes.map(e => `
        <div class="item-card">
          <div class="item-header">
            <span class="item-id">${e.title || e.id} <span style="font-weight:normal; color:var(--text-muted)">(${e.topic})</span></span>
            <span class="pill ${e.status}">${e.status}</span>
          </div>
          <div class="item-body">${escapeHtml(e.narrative)}</div>
          <div class="item-meta">
            <span><b>Period:</b> ${e.period || '-'}</span>
            <span><b>Entities:</b> ${escapeHtml(e.entities || '-')}</span>
            <span><b>Stance / Sentiment:</b> ${escapeHtml(e.stance || '-')}</span>
          </div>
        </div>
      `).join('');
    }

    function renderLearnings(learnings) {
      const cont = document.getElementById('learnings-items');
      if (!learnings || learnings.length === 0) {
        cont.innerHTML = '<p style="color:var(--text-muted); padding:20px; text-align:center;">No learnings stored.</p>';
        return;
      }
      cont.innerHTML = learnings.map(l => `
        <div class="item-card">
          <div class="item-header">
            <span class="item-id">${l.id}</span>
            <span class="pill category">${l.category}</span>
          </div>
          <div class="item-body">💡 ${escapeHtml(l.insight)}</div>
          <div class="item-meta">
            <span><b>Context:</b> ${escapeHtml(l.context || '-')}</span>
            <span><b>Keywords:</b> ${escapeHtml(l.keywords || '-')}</span>
          </div>
        </div>
      `).join('');
    }

    function renderGraph(links) {
      const cont = document.getElementById('graph-items');
      if (!links || links.length === 0) {
        cont.innerHTML = '<p style="color:var(--text-muted); padding:20px; text-align:center;">No entity relationships stored.</p>';
        return;
      }
      cont.innerHTML = links.map(l => `
        <div class="graph-card">
          <div class="graph-node">${l.source_id}</div>
          <div class="graph-arrow">
            <span>➔</span>
            <span class="graph-relation">${l.relation}</span>
          </div>
          <div class="graph-node">${l.target_id}</div>
        </div>
      `).join('');
    }

    function renderAudit(audit) {
      const cont = document.getElementById('audit-items');
      if (!audit || audit.length === 0) {
        cont.innerHTML = '<p style="color:var(--text-muted); padding:20px; text-align:center;">No consolidation logs recorded.</p>';
        return;
      }
      cont.innerHTML = audit.map(a => `
        <div class="item-card">
          <div class="item-header">
            <span class="item-id">${a.action.toUpperCase()}: ${a.target_id}</span>
            <span class="pill category">${a.category}</span>
          </div>
          <div class="item-body"><b>Change:</b> ${escapeHtml(a.diff_summary)}</div>
          <div class="item-meta">
            <span><b>Rationale:</b> ${escapeHtml(a.rationale)}</span>
            <span><b>Timestamp:</b> ${a.timestamp}</span>
          </div>
        </div>
      `).join('');
    }

    function debounceSearch() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(runSearch, 150);
    }

    async function runSearch() {
      const q = document.getElementById('inp-search').value.trim();
      const cont = document.getElementById('search-results');
      const latLbl = document.getElementById('search-latency');
      if (!q) {
        cont.innerHTML = '<p style="color:var(--text-muted); text-align:center; padding: 40px;">Type a search query to test hybrid retrieval.</p>';
        latLbl.innerText = '0 ms';
        return;
      }

      const t0 = performance.now();
      try {
        const res = await fetch('/api/search?q=' + encodeURIComponent(q));
        const data = await res.json();
        const t1 = performance.now();
        latLbl.innerText = `${(t1 - t0).toFixed(1)} ms (${data.tokens ? data.tokens.join(', ') : ''})`;

        let html = '';
        if (data.facts && data.facts.length > 0) {
          html += '<h4 style="color:var(--accent); margin:15px 0 10px;">🧱 Matches in Facts</h4>' + data.facts.map(f => `
            <div class="item-card">
              <div class="item-header"><span class="item-id">${f.id}</span><span class="pill category">${f.category}</span></div>
              <div class="item-body">${escapeHtml(f.fact)}</div>
            </div>
          `).join('');
        }
        if (data.episodes && data.episodes.length > 0) {
          html += '<h4 style="color:var(--purple); margin:15px 0 10px;">📖 Matches in Episodes</h4>' + data.episodes.map(e => `
            <div class="item-card">
              <div class="item-header"><span class="item-id">${e.title}</span><span class="pill ${e.status}">${e.status}</span></div>
              <div class="item-body">${escapeHtml(e.narrative)}</div>
            </div>
          `).join('');
        }
        if (data.learnings && data.learnings.length > 0) {
          html += '<h4 style="color:var(--cyan); margin:15px 0 10px;">💡 Matches in Learnings</h4>' + data.learnings.map(l => `
            <div class="item-card">
              <div class="item-header"><span class="item-id">${l.id}</span><span class="pill category">${l.category}</span></div>
              <div class="item-body">${escapeHtml(l.insight)}</div>
            </div>
          `).join('');
        }

        if (!html) {
          html = '<p style="color:var(--text-muted); text-align:center; padding: 30px;">No matches found for "' + escapeHtml(q) + '"</p>';
        }
        cont.innerHTML = html;
      } catch (e) {
        cont.innerHTML = '<p style="color:var(--danger); text-align:center; padding: 20px;">Search request failed</p>';
      }
    }

    async function forceWorker() {
      if (!confirm('Process pending conversation queue immediately without waiting for debounce timeout?')) return;
      try {
        const res = await fetch('/api/force-worker', { method: 'POST' });
        const data = await res.json();
        alert(data.message || 'Worker finished successfully!');
        fetchData();
      } catch (e) {
        alert('Worker execution error: ' + e);
      }
    }

    function escapeHtml(text) {
      if (!text) return '';
      return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    // Auto-refresh every 3 seconds for real-time responsiveness
    fetchData();
    setInterval(fetchData, 3000);
  </script>
</body>
</html>
"""


class MemoryDashboardHandler(BaseHTTPRequestHandler):
    """Zero-dependency HTTP request handler for AGY Memory Engine Debug Dashboard."""

    def log_message(self, format, *args):
        # Suppress noisy standard request logging
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        params = urllib.parse.parse_qs(url.query)

        if path == "/" or path == "/index.html":
            self._send_html(HTML_TEMPLATE)
            return

        if path == "/favicon.ico":
            svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🧠</text></svg>'
            body = svg.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/stats":
            self._handle_stats()
            return

        if path == "/api/search":
            q = params.get("q", [""])[0]
            self._handle_search(q)
            return

        self._send_json({"error": "Not Found"}, status=404)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/api/force-worker":
            import subprocess
            try:
                worker_bin = BASE_DIR / "memory_worker.py"
                res = subprocess.run([sys.executable, str(worker_bin), "--force"], capture_output=True, text=True, timeout=60)
                self._send_json({"status": "ok", "message": res.stdout.strip() or "Queue processed successfully."})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=500)
            return

        self._send_json({"error": "Not Found"}, status=404)

    def _handle_stats(self):
        try:
            with db_session() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM memories")
                cnt_facts = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM episodes")
                cnt_episodes = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM learnings")
                cnt_learnings = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM entity_links")
                cnt_links = cursor.fetchone()[0]

                # Fetch all facts
                cursor.execute("SELECT id, category, fact, keywords, updated_at FROM memories ORDER BY updated_at DESC")
                facts = [{"id": r[0], "category": r[1], "fact": r[2], "keywords": r[3], "updated_at": str(r[4])} for r in cursor.fetchall()]

                # Fetch all episodes
                cursor.execute("SELECT id, topic, title, period, status, narrative, entities, stance, updated_at FROM episodes ORDER BY updated_at DESC")
                episodes = [{"id": r[0], "topic": r[1], "title": r[2], "period": r[3], "status": r[4], "narrative": r[5], "entities": r[6], "stance": r[7], "updated_at": str(r[8])} for r in cursor.fetchall()]

                # Fetch all learnings
                cursor.execute("SELECT id, category, insight, context, keywords, updated_at FROM learnings ORDER BY updated_at DESC")
                learnings = [{"id": r[0], "category": r[1], "insight": r[2], "context": r[3], "keywords": r[4], "updated_at": str(r[5])} for r in cursor.fetchall()]

                # Fetch all links
                cursor.execute("SELECT source_id, target_id, relation FROM entity_links ORDER BY source_id")
                links = [{"source_id": r[0], "target_id": r[1], "relation": r[2]} for r in cursor.fetchall()]

                # Fetch audit log
                cursor.execute("SELECT action, category, target_id, diff_summary, rationale, timestamp FROM consolidation_log ORDER BY id DESC LIMIT 50")
                audit = [{"action": r[0], "category": r[1], "target_id": r[2], "diff_summary": r[3], "rationale": r[4], "timestamp": str(r[5])} for r in cursor.fetchall()]

            # Queue stats
            q_stats = get_pending_stats()
            q_turns = get_pending_turns(limit=25)

            # DB file size
            db_size = "-"
            if os.path.exists(DB_PATH):
                sz = os.path.getsize(DB_PATH)
                db_size = f"{sz / 1024:.1f} KB" if sz < 1024 * 1024 else f"{sz / (1024*1024):.2f} MB"

            self._send_json({
                "model": MODEL_NAME,
                "db_path": DB_PATH,
                "db_size": db_size,
                "counts": {
                    "facts": cnt_facts,
                    "episodes": cnt_episodes,
                    "learnings": cnt_learnings,
                    "links": cnt_links,
                    "queue_pending": q_stats.get("count", 0)
                },
                "queue": {
                    "pending_count": q_stats.get("count", 0),
                    "newest_age_seconds": q_stats.get("newest_age_seconds", 0),
                    "oldest_age_seconds": q_stats.get("oldest_age_seconds", 0),
                    "turns": q_turns
                },
                "facts": facts,
                "episodes": episodes,
                "learnings": learnings,
                "links": links,
                "audit": audit
            })
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_search(self, q: str):
        if not q.strip():
            self._send_json({"facts": [], "episodes": [], "learnings": [], "tokens": []})
            return

        try:
            with db_session() as conn:
                cursor = conn.cursor()
                vocab = get_all_vocabulary(cursor)
                words = extract_multilingual_tokens(q, vocab)
                if not words:
                    self._send_json({"facts": [], "episodes": [], "learnings": [], "tokens": []})
                    return

                fts_terms = [f'"{w}"*' if len(w) >= 4 else f'"{w}"' for w in words]
                fts_query = " OR ".join(fts_terms)

                # Query Facts
                cursor.execute("""
                    SELECT m.id, m.category, m.fact 
                    FROM memories m
                    JOIN memories_fts f ON m.id = f.id
                    WHERE memories_fts MATCH ?
                    ORDER BY f.rank LIMIT 10;
                """, (fts_query,))
                facts = [{"id": r[0], "category": r[1], "fact": r[2]} for r in cursor.fetchall()]

                # Query Episodes
                cursor.execute("""
                    SELECT e.id, e.topic, e.title, e.period, e.status, e.narrative 
                    FROM episodes e
                    JOIN episodes_fts f ON e.id = f.id
                    WHERE episodes_fts MATCH ?
                    ORDER BY f.rank LIMIT 10;
                """, (fts_query,))
                episodes = [{"id": r[0], "topic": r[1], "title": r[2], "period": r[3], "status": r[4], "narrative": r[5]} for r in cursor.fetchall()]

                # Query Learnings
                cursor.execute("""
                    SELECT l.id, l.category, l.insight 
                    FROM learnings l
                    JOIN learnings_fts f ON l.id = f.id
                    WHERE learnings_fts MATCH ?
                    ORDER BY f.rank LIMIT 10;
                """, (fts_query,))
                learnings = [{"id": r[0], "category": r[1], "insight": r[2]} for r in cursor.fetchall()]

                self._send_json({
                    "tokens": words,
                    "facts": facts,
                    "episodes": episodes,
                    "learnings": learnings
                })
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)


def run_dashboard(host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT):
    """Start the multi-threaded HTTP server."""
    server = ThreadingHTTPServer((host, port), MemoryDashboardHandler)
    print(f"🚀 AGY Memory Debug Dashboard running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Dashboard stopped.")
        server.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AGY Memory Real-Time Debug Dashboard")
    parser.add_argument("--port", type=int, default=DASHBOARD_PORT, help=f"Server port (default: {DASHBOARD_PORT})")
    parser.add_argument("--host", default=DASHBOARD_HOST, help=f"Server host (default: {DASHBOARD_HOST})")
    args = parser.parse_args()
    run_dashboard(host=args.host, port=args.port)
