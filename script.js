// ===============================================
// AGROTECH EXPERIENCE PUCÓN - INTERACTIVE SCRIPT
// ===============================================

// ========== MOBILE NAVIGATION ==========
const navToggle = document.getElementById('navToggle');
const navMenu = document.getElementById('navMenu');
const navLinks = document.querySelectorAll('.nav-link');

navToggle.addEventListener('click', () => {
    navMenu.classList.toggle('active');
});

// Close menu when clicking on a link
navLinks.forEach(link => {
    link.addEventListener('click', () => {
        navMenu.classList.remove('active');
    });
});

// ========== NAVBAR SCROLL EFFECT ==========
const navbar = document.getElementById('navbar');

window.addEventListener('scroll', () => {
    if (window.scrollY > 100) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }
});

// ========== SMOOTH SCROLLING ==========
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// ========== ANIMATED COUNTERS ==========
const observerOptions = {
    threshold: 0.5,
    rootMargin: '0px 0px -100px 0px'
};

const animateCounter = (element) => {
    const target = parseInt(element.dataset.target);
    const duration = 2000; // 2 seconds
    const increment = target / (duration / 16); // 60fps
    let current = 0;

    const updateCounter = () => {
        current += increment;
        if (current < target) {
            element.textContent = Math.floor(current);
            requestAnimationFrame(updateCounter);
        } else {
            element.textContent = target;
        }
    };

    updateCounter();
};

const counterObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting && !entry.target.classList.contains('counted')) {
            animateCounter(entry.target);
            entry.target.classList.add('counted');
        }
    });
}, observerOptions);

document.querySelectorAll('.stat-number').forEach(counter => {
    counterObserver.observe(counter);
});

// ========== FADE IN ANIMATION ON SCROLL ==========
const fadeElements = document.querySelectorAll('.feature-card, .program-card, .service-card, .pillar-card, .benchmark-card');

const fadeObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('fade-in', 'visible');
        }
    });
}, observerOptions);

fadeElements.forEach(element => {
    element.classList.add('fade-in');
    fadeObserver.observe(element);
});

// ========== FAQ ACCORDION ==========
const faqItems = document.querySelectorAll('.faq-item');

faqItems.forEach(item => {
    const question = item.querySelector('.faq-question');

    question.addEventListener('click', () => {
        // Close other FAQs
        faqItems.forEach(otherItem => {
            if (otherItem !== item && otherItem.classList.contains('active')) {
                otherItem.classList.remove('active');
            }
        });

        // Toggle current FAQ
        item.classList.toggle('active');
    });
});

// ========== NEWSLETTER FORM ==========
const newsletterForm = document.getElementById('newsletterForm');

newsletterForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = newsletterForm.querySelector('input[type="email"]').value;

    // Here you would typically send the email to your backend
    alert(`¡Gracias por suscribirte! Te enviaremos actualizaciones a ${email}`);
    newsletterForm.reset();
});

// ========== STICKY CTA VISIBILITY ==========
const stickyCta = document.getElementById('stickyCta');
const finalCtaSection = document.querySelector('.final-cta-section');

const stickyObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            stickyCta.style.display = 'none';
        } else {
            stickyCta.style.display = 'block';
        }
    });
}, {
    threshold: 0.1
});

if (window.innerWidth <= 768) {
    stickyObserver.observe(finalCtaSection);
}

// ========== ANIMATED METRICS BARS ==========
const metricBars = document.querySelectorAll('.metric-fill');

const metricsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const width = entry.target.style.width;
            entry.target.style.width = '0';
            setTimeout(() => {
                entry.target.style.width = width;
            }, 100);
        }
    });
}, observerOptions);

metricBars.forEach(bar => {
    metricsObserver.observe(bar);
});

// ========== SIMULATED REAL-TIME DATA ==========
// Simulate AI dashboard updates
const updateDashboard = () => {
    const metrics = [
        { label: 'Temperatura', min: 20, max: 25, unit: '°C', selector: '.metric:nth-child(1) .metric-value' },
        { label: 'Humedad', min: 80, max: 95, unit: '%', selector: '.metric:nth-child(2) .metric-value' },
        { label: 'CO₂', min: 800, max: 900, unit: ' ppm', selector: '.metric:nth-child(3) .metric-value' },
        { label: 'Luz', min: 11, max: 14, unit: 'k lux', selector: '.metric:nth-child(4) .metric-value' }
    ];

    metrics.forEach(metric => {
        const element = document.querySelector(metric.selector);
        if (element) {
            const randomValue = (Math.random() * (metric.max - metric.min) + metric.min).toFixed(1);
            element.textContent = randomValue + metric.unit;
        }
    });
};

// Update dashboard every 5 seconds
setInterval(updateDashboard, 5000);

// ========== AI LOG SIMULATOR ==========
const aiLog = document.querySelector('.ai-log');
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

    const logEntries = aiLog.querySelectorAll('.log-entry');
    const randomMessage = logMessages[Math.floor(Math.random() * logMessages.length)];
    const now = new Date();
    const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

    const newEntry = document.createElement('div');
    newEntry.className = 'log-entry';
    newEntry.textContent = `${time} - ${randomMessage}`;
    newEntry.style.opacity = '0';
    newEntry.style.transform = 'translateY(-10px)';

    // Insert at the beginning
    if (logEntries.length > 0) {
        aiLog.insertBefore(newEntry, logEntries[0]);
    } else {
        aiLog.appendChild(newEntry);
    }

    // Animate in
    setTimeout(() => {
        newEntry.style.transition = 'all 0.3s ease';
        newEntry.style.opacity = '1';
        newEntry.style.transform = 'translateY(0)';
    }, 100);

    // Keep only the last 3 entries
    if (logEntries.length >= 3) {
        logEntries[logEntries.length - 1].remove();
    }
};

// Add new log entry every 8 seconds
setInterval(addLogEntry, 8000);

// ========== AI ANNOTATIONS ANIMATION ==========
const updateAnnotations = () => {
    const annotations = document.querySelectorAll('.annotation');
    const mushroomCount = Math.floor(Math.random() * 10) + 30;
    const dayCount = Math.floor(Math.random() * 5) + 10;
    const humidity = Math.floor(Math.random() * 8) + 82;
    const harvestHours = Math.floor(Math.random() * 24) + 36;

    const updates = [
        `Día ${dayCount} de cultivo`,
        `${mushroomCount} hongos shiitake detectados`,
        `Humedad óptima: ${humidity}%`,
        `Cosecha estimada: ${harvestHours} horas`
    ];

    annotations.forEach((annotation, index) => {
        if (updates[index]) {
            annotation.textContent = updates[index];
        }
    });
};

// Update annotations every 10 seconds
setInterval(updateAnnotations, 10000);

// ========== PARALLAX EFFECT ==========
window.addEventListener('scroll', () => {
    const scrolled = window.pageYOffset;
    const parallaxElements = document.querySelectorAll('.hero-background');

    parallaxElements.forEach(element => {
        element.style.transform = `translateY(${scrolled * 0.5}px)`;
    });
});

// ========== INTERSECTION OBSERVER FOR SECTIONS ==========
const sections = document.querySelectorAll('section');

const sectionObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, {
    threshold: 0.1
});

sections.forEach(section => {
    section.style.opacity = '0';
    section.style.transform = 'translateY(20px)';
    section.style.transition = 'all 0.6s ease';
    sectionObserver.observe(section);
});

// ========== INITIALIZE ON LOAD ==========
document.addEventListener('DOMContentLoaded', () => {
    // Set initial dashboard values
    updateDashboard();
    updateAnnotations();

    // Add initial log entries
    addLogEntry();
    setTimeout(addLogEntry, 3000);
    setTimeout(addLogEntry, 6000);

    console.log('🌱 Agrotech Experience Pucón - Website Loaded Successfully');
});

// ========== EASTER EGG: KONAMI CODE ==========
const konamiCode = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];
let konamiIndex = 0;

document.addEventListener('keydown', (e) => {
    if (e.key === konamiCode[konamiIndex]) {
        konamiIndex++;
        if (konamiIndex === konamiCode.length) {
            document.body.style.filter = 'hue-rotate(180deg)';
            alert('🍄 ¡Modo Hongos Psicodélicos Activado! 🍄');
            konamiIndex = 0;
            setTimeout(() => {
                document.body.style.filter = 'none';
            }, 5000);
        }
    } else {
        konamiIndex = 0;
    }
});
