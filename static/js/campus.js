/* ══════════════════════════════════════════
   Smart Campus Platform — Main JS
   Theme · Chatbot · Charts · PWA · Voice
   ══════════════════════════════════════════ */

'use strict';

// ── Theme Toggle ──────────────────────────────
const ThemeManager = {
  KEY: 'campus-theme',
  init() {
    const saved = localStorage.getItem(this.KEY) || 'light';
    this.apply(saved);
  },
  apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(this.KEY, theme);
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
  },
  toggle() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    this.apply(current === 'dark' ? 'light' : 'dark');
  }
};

// ── Mobile Sidebar ────────────────────────────
const SidebarManager = {
  init() {
    const ham = document.querySelector('.hamburger');
    const sidebar = document.querySelector('.campus-sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    if (!ham || !sidebar) return;
    ham.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      overlay?.classList.toggle('visible');
    });
    overlay?.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('visible');
    });
  }
};

// ── Animated Counters ─────────────────────────
const CounterManager = {
  init() {
    const els = document.querySelectorAll('[data-count]');
    els.forEach(el => {
      const target = parseFloat(el.dataset.count);
      const suffix = el.dataset.suffix || '';
      const duration = 1200;
      const start = Date.now();
      const isFloat = String(target).includes('.');
      const tick = () => {
        const elapsed = Date.now() - start;
        const progress = Math.min(elapsed / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 3);
        const current = target * ease;
        el.textContent = (isFloat ? current.toFixed(1) : Math.floor(current)) + suffix;
        if (progress < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }
};

// ── AI Chatbot ────────────────────────────────
const ChatBot = {
  ENDPOINT: '/campus/assistant/chat',
  init() {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('chat-input');
    const messages = document.getElementById('chat-messages');
    const voiceBtn = document.getElementById('voice-btn');
    if (!form || !messages) return;

    // Send on form submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      input.value = '';
      this.addBubble(messages, 'user', text);
      const typing = this.showTyping(messages);
      const reply = await this.send(text);
      typing.remove();
      this.addBubble(messages, 'bot', reply);
      this.speak(reply);
      messages.scrollTop = messages.scrollHeight;
    });

    // Voice input
    if (voiceBtn && 'webkitSpeechRecognition' in window) {
      const recog = new webkitSpeechRecognition();
      recog.continuous = false;
      recog.lang = document.documentElement.lang || 'en-US';
      recog.onstart = () => voiceBtn.classList.add('listening');
      recog.onend = () => voiceBtn.classList.remove('listening');
      recog.onresult = (e) => {
        input.value = e.results[0][0].transcript;
        form.dispatchEvent(new Event('submit'));
      };
      voiceBtn.addEventListener('click', () => recog.start());
    } else if (voiceBtn) {
      voiceBtn.style.display = 'none';
    }

    // Quick chips
    document.querySelectorAll('.quick-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        input.value = chip.textContent.trim();
        form.dispatchEvent(new Event('submit'));
      });
    });

    // Language selector
    const langSel = document.getElementById('lang-select');
    if (langSel) {
      langSel.addEventListener('change', () => {
        document.documentElement.lang = langSel.value;
      });
    }
  },

  addBubble(container, role, text) {
    const row = document.createElement('div');
    row.className = `chat-row ${role === 'user' ? 'user-row' : ''}`;

    if (role === 'bot') {
      const avatar = document.createElement('div');
      avatar.className = 'bot-avatar';
      avatar.textContent = '🤖';
      row.appendChild(avatar);
    }

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${role}`;
    // Render **bold** markdown
    bubble.innerHTML = this.renderMd(text);
    row.appendChild(bubble);
    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
  },

  renderMd(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  },

  showTyping(container) {
    const row = document.createElement('div');
    row.className = 'chat-row';
    const avatar = document.createElement('div');
    avatar.className = 'bot-avatar';
    avatar.textContent = '🤖';
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble bot';
    bubble.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
    row.appendChild(avatar);
    row.appendChild(bubble);
    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
    return row;
  },

  async send(message) {
    try {
      const resp = await fetch(this.ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('meta[name=csrf-token]')?.content || ''
        },
        body: JSON.stringify({ message })
      });
      const data = await resp.json();
      return data.reply || 'Sorry, I could not process that.';
    } catch (err) {
      return '❌ Network error — please try again.';
    }
  },

  speak(text) {
    if (!window.speechSynthesis) return;
    const plain = text.replace(/[*#_`]/g, '').replace(/<[^>]+>/g, '');
    const utt = new SpeechSynthesisUtterance(plain.slice(0, 200));
    utt.lang = document.documentElement.lang || 'en-US';
    utt.rate = 0.95;
    window.speechSynthesis.speak(utt);
  }
};

// ── Chart Helpers ─────────────────────────────
const ChartManager = {
  defaults: {
    font: { family: 'Inter, sans-serif' },
    color: '#6b7280',
    plugins: { legend: { labels: { color: '#6b7280', font: { family: 'Inter' } } } }
  },

  gradient(ctx, colors) {
    const grad = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
    grad.addColorStop(0, colors[0]);
    grad.addColorStop(1, colors[1]);
    return grad;
  },

  line(canvasId, labels, datasets, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    return new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { ...this.defaults.plugins, ...options.plugins },
        scales: {
          x: { grid: { color: 'rgba(102,126,234,0.08)' }, ticks: { color: '#9ca3af', font: { family: 'Inter' } } },
          y: { grid: { color: 'rgba(102,126,234,0.08)' }, ticks: { color: '#9ca3af', font: { family: 'Inter' } }, ...options.yAxis }
        },
        ...options
      }
    });
  },

  bar(canvasId, labels, datasets, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    return new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { ...this.defaults.plugins, ...options.plugins },
        scales: {
          x: { grid: { display: false }, ticks: { color: '#9ca3af', font: { family: 'Inter' } } },
          y: { grid: { color: 'rgba(102,126,234,0.08)' }, ticks: { color: '#9ca3af', font: { family: 'Inter' } } }
        },
        ...options
      }
    });
  },

  doughnut(canvasId, labels, data, colors) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    return new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{ data, backgroundColor: colors, borderWidth: 0, hoverOffset: 6 }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        plugins: {
          legend: { position: 'bottom', labels: { color: '#9ca3af', font: { family: 'Inter' }, padding: 16 } }
        }
      }
    });
  }
};

// ── Notification Badge Updater ────────────────
const NotifBadge = {
  init() {
    const badge = document.getElementById('notif-badge-count');
    if (!badge) return;
    const update = async () => {
      try {
        const res = await fetch('/campus/api/notification-count');
        const data = await res.json();
        if (data.count > 0) {
          badge.textContent = data.count;
          badge.style.display = 'inline-flex';
        } else {
          badge.style.display = 'none';
        }
      } catch {}
    };
    update();
    setInterval(update, 60000);
  }
};

// ── Flash Message Auto-dismiss ────────────────
const FlashManager = {
  init() {
    document.querySelectorAll('.campus-flash').forEach(el => {
      setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(-10px)';
        setTimeout(() => el.remove(), 400);
      }, 4000);
    });
  }
};

// ── Modal Helpers ─────────────────────────────
window.openModal = (id) => {
  const modal = document.getElementById(id);
  if (modal) { modal.style.display = 'flex'; document.body.style.overflow = 'hidden'; }
};
window.closeModal = (id) => {
  const modal = document.getElementById(id);
  if (modal) { modal.style.display = 'none'; document.body.style.overflow = ''; }
};
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('campus-modal-backdrop')) {
    e.target.style.display = 'none';
    document.body.style.overflow = '';
  }
});

// ── PWA Registration ──────────────────────────
const PWA = {
  init() {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/static/js/sw.js')
        .then(() => console.log('🚀 Smart Campus PWA ready'))
        .catch(() => {});
    }
  }
};

// ── DOM Ready ─────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  ThemeManager.init();
  SidebarManager.init();
  CounterManager.init();
  ChatBot.init();
  NotifBadge.init();
  FlashManager.init();
  PWA.init();

  // Theme toggle button
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.addEventListener('click', () => ThemeManager.toggle());

  // Intersection observer for card animations
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('animate-fade-up');
        observer.unobserve(e.target);
      }
    });
  }, { threshold: 0.08 });
  document.querySelectorAll('.glass-card, .stat-card, .lms-card').forEach(el => observer.observe(el));
});

// Expose globally
window.ThemeManager = ThemeManager;
window.ChartManager = ChartManager;
window.ChatBot = ChatBot;
