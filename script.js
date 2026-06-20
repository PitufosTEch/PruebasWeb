// ===============================================
// AGROTECH EXPERIENCE PUCÓN - INTERACTIVE SCRIPT
// ===============================================

// ========== CACHED DOM REFERENCES ==========
const navToggle = document.getElementById('navToggle');
const navMenu   = document.getElementById('navMenu');
const navbar    = document.getElementById('navbar');
const stickyCta = document.getElementById('stickyCta');
const finalCtaSection = document.querySelector('.final-cta-section');
const aiLog           = document.querySelector('.ai-log');
const annotationEls   = document.querySelectorAll('.annotation');
const heroBackground  = document.querySelector('.hero-background');

// Cache metric value elements to avoid repeated DOM queries inside setInterval
const metricEls = [
    document.querySelector('.metric:nth-child(1) .metric-value'),
    document.querySelector('.metric:nth-child(2) .metric-value'),
    document.querySelector('.metric:nth-child(3) .metric-value'),
    document.querySelector('.metric:nth-child(4) .metric-value')
];

// Compute once at load — avoids per-scroll matchMedia calls
const isMobile = window.matchMedia('(max-width: 768px)').matches;

// ========== MOBILE NAVIGATION ==========
navToggle.addEventListener('click', () => navMenu.classList.toggle('active'));

document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => navMenu.classList.remove('active'));
});

// ========== SMOOTH SCROLLING ==========
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// ========== SINGLE THROTTLED SCROLL HANDLER ==========
// Combines navbar + parallax into one rAF-throttled listener with passive flag
let scrollPending = false;

window.addEventListener('scroll', () => {
    if (scrollPending) return;
    scrollPending = true;
    requestAnimationFrame(() => {
        const y = window.scrollY;
        navbar.classList.toggle('scrolled', y > 100);
        // Parallax is expensive on mobile — skip it
        if (!isMobile && heroBackground) {
            heroBackground.style.transform = `translateY(${y * 0.5}px)`;
        }
        scrollPending = false;
    });
}, { passive: true });

// ========== SHARED OBSERVER OPTIONS ==========
const halfThreshold  = { threshold: 0.5, rootMargin: '0px 0px -100px 0px' };
const tenthThreshold = { threshold: 0.1 };

// ========== ANIMATED COUNTERS ==========
const animateCounter = (el) => {
    const target    = parseInt(el.dataset.target);
    const increment = target / (2000 / 16); // 2 s at ~60 fps
    let current = 0;
    const tick = () => {
        current += increment;
        if (current < target) {
            el.textContent = Math.floor(current);
            requestAnimationFrame(tick);
        } else {
            el.textContent = target;
        }
    };
    tick();
};

const counterObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        animateCounter(entry.target);
        entry.target.classList.add('counted');
        counterObserver.unobserve(entry.target); // fire-once
    });
}, halfThreshold);

document.querySelectorAll('.stat-number').forEach(el => counterObserver.observe(el));

// ========== FADE IN CARDS ==========
const fadeObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('visible');
        fadeObserver.unobserve(entry.target); // fire-once
    });
}, halfThreshold);

document.querySelectorAll('.feature-card, .program-card, .service-card, .pillar-card, .benchmark-card')
    .forEach(el => {
        el.classList.add('fade-in');
        fadeObserver.observe(el);
    });

// ========== SECTION ENTRANCE ANIMATION ==========
// Skip .hero — it's immediately visible and has its own CSS animations
const sectionObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('section-visible');
        sectionObserver.unobserve(entry.target); // fire-once
    });
}, tenthThreshold);

document.querySelectorAll('section:not(.hero)').forEach(section => {
    section.classList.add('section-hidden');
    sectionObserver.observe(section);
});

// ========== METRIC BARS ANIMATION ==========
// Store target widths before zeroing to avoid reading style.width after reset
const metricBars = document.querySelectorAll('.metric-fill');
metricBars.forEach(bar => {
    bar.dataset.targetWidth = bar.style.width;
    bar.style.width = '0';
});

const metricsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const bar = entry.target;
        setTimeout(() => { bar.style.width = bar.dataset.targetWidth; }, 100);
        metricsObserver.unobserve(bar); // fire-once
    });
}, tenthThreshold);

metricBars.forEach(bar => metricsObserver.observe(bar));

// ========== STICKY CTA ==========
if (isMobile && finalCtaSection) {
    const stickyObserver = new IntersectionObserver(([entry]) => {
        stickyCta.style.display = entry.isIntersecting ? 'none' : 'block';
    }, tenthThreshold);
    stickyObserver.observe(finalCtaSection);
}

// ========== FAQ ACCORDION ==========
document.querySelectorAll('.faq-item').forEach(item => {
    item.querySelector('.faq-question').addEventListener('click', () => {
        const isActive = item.classList.contains('active');
        document.querySelectorAll('.faq-item.active').forEach(open => open.classList.remove('active'));
        if (!isActive) item.classList.add('active');
    });
});

// ========== NEWSLETTER FORM ==========
document.getElementById('newsletterForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const btn  = form.querySelector('button[type="submit"]');
    const original = btn.textContent;
    btn.textContent = '✓ ¡Suscrito!';
    btn.disabled = true;
    setTimeout(() => {
        btn.textContent = original;
        btn.disabled = false;
        form.reset();
    }, 3000);
});

// ========== REAL-TIME DASHBOARD ==========
const metricConfig = [
    { min: 20,  max: 25,  unit: '°C'    },
    { min: 80,  max: 95,  unit: '%'     },
    { min: 800, max: 900, unit: ' ppm'  },
    { min: 11,  max: 14,  unit: 'k lux' }
];

const updateDashboard = () => {
    metricEls.forEach((el, i) => {
        if (!el) return;
        const { min, max, unit } = metricConfig[i];
        el.textContent = (Math.random() * (max - min) + min).toFixed(1) + unit;
    });
};

// ========== AI LOG SIMULATOR ==========
const logMessages = [
    'IA detectó baja humedad → Activó nebulizador 30 seg',
    'Temperatura alta → Incrementó ventilación',
    'Ciclo de luz completado → Ajustando espectro',
    'Nuevo brote detectado → Actualizando contador',
    'Nivel de CO₂ óptimo → Manteniendo parámetros',
    'Humedad estabilizada → Sistema en equilibrio',
    'Análisis de crecimiento → Predicción: 48h para cosecha',
    'Sensor de temperatura calibrado correctamente'
];

const addLogEntry = () => {
    if (!aiLog) return;
    const entries = aiLog.querySelectorAll('.log-entry');
    const now  = new Date();
    const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    const msg  = logMessages[Math.floor(Math.random() * logMessages.length)];

    const entry = document.createElement('div');
    entry.className   = 'log-entry';
    entry.textContent = `${time} - ${msg}`;
    entry.style.cssText = 'opacity:0;transform:translateY(-10px)';

    aiLog.insertBefore(entry, entries[0] || null);

    // Force reflow so initial styles paint before transition starts
    entry.getBoundingClientRect();
    entry.style.cssText = 'transition:opacity 0.3s ease,transform 0.3s ease;opacity:1;transform:none';

    if (entries.length >= 3) entries[entries.length - 1].remove();
};

// ========== AI ANNOTATIONS ==========
const updateAnnotations = () => {
    const values = [
        `Día ${Math.floor(Math.random() * 5) + 10} de cultivo`,
        `${Math.floor(Math.random() * 10) + 30} hongos shiitake detectados`,
        `Humedad óptima: ${Math.floor(Math.random() * 8) + 82}%`,
        `Cosecha estimada: ${Math.floor(Math.random() * 24) + 36} horas`
    ];
    annotationEls.forEach((el, i) => { el.textContent = values[i]; });
};

// ========== INTERVAL MANAGEMENT (Page Visibility API) ==========
// Pause all intervals when the tab is hidden to save CPU and battery
let timers = [];

const startTimers = () => {
    stopTimers(); // guard against duplicates
    timers = [
        setInterval(updateDashboard,   5000),
        setInterval(addLogEntry,        8000),
        setInterval(updateAnnotations, 10000)
    ];
};

const stopTimers = () => {
    timers.forEach(clearInterval);
    timers = [];
};

document.addEventListener('visibilitychange', () => {
    document.hidden ? stopTimers() : startTimers();
});

// ========== INITIALIZE ON DOM READY ==========
document.addEventListener('DOMContentLoaded', () => {
    updateDashboard();
    updateAnnotations();
    addLogEntry();
    setTimeout(addLogEntry, 3000);
    setTimeout(addLogEntry, 6000);
    startTimers();
    console.log('🌱 Agrotech Experience Pucón - Website Loaded Successfully');
});

// ========== EASTER EGG: KONAMI CODE ==========
const konami = ['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];
let ki = 0;
document.addEventListener('keydown', ({ key }) => {
    ki = key === konami[ki] ? ki + 1 : 0;
    if (ki === konami.length) {
        document.body.style.filter = 'hue-rotate(180deg)';
        ki = 0;
        setTimeout(() => { document.body.style.filter = ''; }, 5000);
    }
});
