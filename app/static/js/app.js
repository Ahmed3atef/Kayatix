// AI HR Copilot Client-side JavaScript

// Toast Notification Utility
function showToast(message, type = 'primary') {
    const toastEl = document.getElementById('liveToast');
    const toastBody = document.getElementById('toastMessage');
    if (!toastEl || !toastBody) return;

    toastEl.className = `toast align-items-center text-bg-${type} border-0 shadow`;
    toastBody.innerText = message;

    const toast = bootstrap.Toast.getOrCreateInstance(toastEl);
    toast.show();
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

// Copy to Clipboard Utility
function copyToClipboard(text, successMsg = 'Copied to clipboard!') {
    navigator.clipboard.writeText(text).then(() => {
        showToast(successMsg, 'success');
    }).catch(err => {
        showToast('Failed to copy: ' + err, 'danger');
    });
}

// Theme Toggle (Light / Dark)
const themeToggleBtn = document.getElementById('themeToggleBtn');
if (themeToggleBtn) {
    const themeIcon = document.getElementById('themeIcon');
    const savedTheme = localStorage.getItem('hrcopilot_theme') || 'light';
    document.documentElement.setAttribute('data-bs-theme', savedTheme);
    updateThemeIcon(savedTheme);

    themeToggleBtn.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-bs-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-bs-theme', next);
        localStorage.setItem('hrcopilot_theme', next);
        updateThemeIcon(next);
    });

    function updateThemeIcon(theme) {
        if (themeIcon) {
            themeIcon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars';
        }
    }
}

function formatProviderBadge(provider) {
    if (!provider) return '<span class="badge bg-secondary-subtle text-secondary font-monospace">Unknown</span>';
    const p = String(provider).toLowerCase();
    if (p.includes('google') || p.includes('gemini')) {
        return `<span class="badge bg-primary-subtle text-primary border border-primary-subtle font-monospace"><i class="bi bi-stars me-1"></i>${provider}</span>`;
    }
    if (p.includes('groq')) {
        return `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle font-monospace"><i class="bi bi-lightning-charge-fill me-1"></i>${provider}</span>`;
    }
    if (p.includes('ollama')) {
        return `<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle font-monospace"><i class="bi bi-cloud me-1"></i>${provider}</span>`;
    }
    return `<span class="badge bg-secondary-subtle text-secondary border font-monospace">${provider}</span>`;
}

// Render Evaluation Scorecard Card
function buildEvaluationCardHTML(apiData) {
    const res = apiData.analysis;
    const isCached = apiData.cached;
    const provider = apiData.provider_used;

    let scoreBadge = '';
    if (res.match_percentage >= 85) {
        scoreBadge = `<span class="badge bg-success fs-5 px-3 py-2 rounded-pill"><i class="bi bi-check-circle-fill me-1"></i> ${res.match_percentage}% Match</span>`;
    } else if (res.match_percentage >= 70) {
        scoreBadge = `<span class="badge bg-primary fs-5 px-3 py-2 rounded-pill"><i class="bi bi-check-circle-fill me-1"></i> ${res.match_percentage}% Match</span>`;
    } else if (res.match_percentage >= 50) {
        scoreBadge = `<span class="badge bg-warning text-dark fs-5 px-3 py-2 rounded-pill"><i class="bi bi-exclamation-circle-fill me-1"></i> ${res.match_percentage}% Match</span>`;
    } else {
        scoreBadge = `<span class="badge bg-danger fs-5 px-3 py-2 rounded-pill"><i class="bi bi-x-circle-fill me-1"></i> ${res.match_percentage}% Match</span>`;
    }

    const rec = res.hiring_recommendation || (res.match_percentage >= 85 ? 'Strong Hire' : (res.match_percentage >= 70 ? 'Proceed (Technical Screen)' : (res.match_percentage >= 50 ? 'Borderline (Phone Screen First)' : 'Reject / Not Recommended')));
    let recClass = 'bg-secondary';
    if (rec.includes('Strong')) recClass = 'bg-success-subtle text-success border border-success-subtle';
    else if (rec.includes('Proceed')) recClass = 'bg-primary-subtle text-primary border border-primary-subtle';
    else if (rec.includes('Borderline')) recClass = 'bg-warning-subtle text-warning-emphasis border border-warning-subtle';
    else if (rec.includes('Reject')) recClass = 'bg-danger-subtle text-danger border border-danger-subtle';

    const recBadge = `<span class="badge ${recClass} fs-7 px-3 py-2 rounded-pill"><i class="bi bi-person-check me-1"></i>${rec}</span>`;

    const matchedSkills = res.matched_skills.map(s => `<span class="badge bg-success-subtle text-success border border-success-subtle me-1 mb-1">${s}</span>`).join('') || '<span class="text-muted small">None verified</span>';
    const missingSkills = res.missing_critical_skills.map(s => `<span class="badge bg-danger-subtle text-danger border border-danger-subtle me-1 mb-1">${s}</span>`).join('') || '<span class="text-success small">None</span>';

    const projectsList = res.detected_projects_and_impact.map(p => `
        <li class="list-group-item d-flex align-items-start gap-2 py-2">
            <i class="bi bi-arrow-right-circle text-primary mt-1"></i>
            <div>${p}</div>
        </li>
    `).join('') || '<li class="list-group-item text-muted">No prominent projects extracted</li>';

    let redFlagsHtml = '';
    if (res.red_flags_and_gaps && res.red_flags_and_gaps.length > 0) {
        const items = res.red_flags_and_gaps.map(f => `<li>${f}</li>`).join('');
        redFlagsHtml = `
            <div class="alert alert-warning border-warning-subtle mb-3">
                <h6 class="fw-bold mb-1 d-flex align-items-center gap-1"><i class="bi bi-exclamation-triangle-fill"></i> Red Flags & Timeline Gaps</h6>
                <ul class="mb-0 ps-3 small">${items}</ul>
            </div>
        `;
    }

    const questionsAccordion = res.tailored_interview_questions.map((q, idx) => `
        <div class="accordion-item mb-2 border rounded-3 overflow-hidden">
            <h2 class="accordion-header" id="dynH${idx}">
                <button class="accordion-button collapsed fw-semibold py-2" type="button" data-bs-toggle="collapse" data-bs-target="#dynC${idx}">
                    <span class="badge bg-primary-subtle text-primary border me-2">${q.category}</span>
                    <span class="text-truncate">${q.question}</span>
                </button>
            </h2>
            <div id="dynC${idx}" class="accordion-collapse collapse" data-bs-parent="#dynAccordion">
                <div class="accordion-body bg-body-tertiary small">
                    <p class="mb-2 fw-semibold text-body-emphasis">${q.question}</p>
                    <div class="mb-2"><strong>Tested Area:</strong> <span class="badge bg-secondary-subtle text-secondary">${q.target_area}</span></div>
                    <div class="mb-3"><strong>Expected Signals:</strong> <div class="p-2 bg-body rounded border">${q.expected_answer_criteria}</div></div>
                    <button class="btn btn-sm btn-outline-secondary" onclick="copyToClipboard('${q.question.replace(/'/g, "\\'")}', 'Question copied!')">
                        <i class="bi bi-clipboard"></i> Copy Question
                    </button>
                </div>
            </div>
        </div>
    `).join('') || '<div class="text-muted small">No questions generated.</div>';

    let extractionBadge = '<span class="badge bg-secondary-subtle text-secondary border font-monospace"><i class="bi bi-file-earmark-pdf me-1"></i>Standard Parser</span>';
    const method = String(apiData.extraction_method || '').toLowerCase();
    if (method.includes('single-shot') || method.includes('multimodal')) {
        extractionBadge = '<span class="badge bg-primary-subtle text-primary border border-primary-subtle font-monospace"><i class="bi bi-stars me-1"></i>Gemini Multimodal (Direct)</span>';
    } else if (method.includes('gemini_vision') || method.includes('gemini-vision')) {
        extractionBadge = '<span class="badge bg-primary-subtle text-primary border border-primary-subtle font-monospace"><i class="bi bi-eye me-1"></i>Gemini Vision OCR</span>';
    } else if (method.includes('llamaparse')) {
        extractionBadge = '<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle font-monospace"><i class="bi bi-cloud-arrow-down me-1"></i>LlamaParse Cloud</span>';
    } else if (method.includes('pypdf')) {
        extractionBadge = '<span class="badge bg-secondary-subtle text-secondary border font-monospace"><i class="bi bi-cpu me-1"></i>pypdf (Local Fallback)</span>';
    }

    return `
        <div class="card border-0 shadow-sm rounded-4 overflow-hidden mb-3">
            <div class="card-header border-bottom p-3 d-flex justify-content-between align-items-center">
                <div>
                    <h5 class="fw-bold mb-0 text-body-emphasis">${res.candidate_name || "Candidate Evaluation"}</h5>
                    <div class="d-flex align-items-center gap-2 small text-muted mt-1 flex-wrap">
                        <span><i class="bi bi-briefcase me-1"></i> ${res.estimated_years_experience} YOE</span>
                        <span>&bull;</span>
                        <span>Parser: ${extractionBadge}</span>
                        <span>&bull;</span>
                        <span>AI Provider: ${formatProviderBadge(provider)}</span>
                        <span>&bull;</span>
                        <span>${isCached ? '<span class="badge bg-success-subtle text-success"><i class="bi bi-check2"></i> Cache Hit</span>' : '<span class="badge bg-primary-subtle text-primary">Live Evaluated</span>'}</span>
                    </div>
                </div>
                <div class="d-flex align-items-center flex-wrap gap-2 justify-content-end">${scoreBadge}${recBadge}</div>
            </div>
            <div class="card-body p-3">
                <div class="mb-3">
                    <h6 class="fw-bold text-uppercase text-secondary small mb-1">Executive Summary</h6>
                    <div class="p-3 bg-body-tertiary rounded-3 border small text-body-emphasis">${res.executive_summary}</div>
                </div>

                <div class="row g-3 mb-3">
                    <div class="col-md-6">
                        <div class="p-3 border rounded-3 bg-body-tertiary h-100">
                            <h6 class="fw-bold text-success mb-2 small"><i class="bi bi-check-circle"></i> Matched Skills</h6>
                            <div>${matchedSkills}</div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="p-3 border rounded-3 bg-body-tertiary h-100">
                            <h6 class="fw-bold text-danger mb-2 small"><i class="bi bi-x-circle"></i> Missing Critical Skills</h6>
                            <div>${missingSkills}</div>
                        </div>
                    </div>
                </div>

                <div class="mb-3">
                    <h6 class="fw-bold text-uppercase text-secondary small mb-1"><i class="bi bi-trophy"></i> Key Projects & Impact</h6>
                    <ul class="list-group list-group-flush border rounded-3 small">${projectsList}</ul>
                </div>

                ${redFlagsHtml}

                <div>
                    <h6 class="fw-bold text-uppercase text-secondary small mb-2"><i class="bi bi-question-diamond"></i> Tailored Interview Questions (${res.tailored_interview_questions.length})</h6>
                    <div class="accordion" id="dynAccordion">${questionsAccordion}</div>
                </div>
            </div>
        </div>
    `;
}

// 1. Resume Screen Form Submission
const resumeForm = document.getElementById('resumeScreenForm');
if (resumeForm) {
    resumeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fileInput = document.getElementById('resumeFile');
        const jdInput = document.getElementById('resumeJdText');
        const btn = document.getElementById('screenResumeBtn');
        const emptyState = document.getElementById('evaluationEmptyState');
        const loading = document.getElementById('evaluationLoading');
        const container = document.getElementById('evaluationResultContainer');

        if (!fileInput.files.length) {
            showToast('Please select a PDF resume file.', 'warning');
            return;
        }

        btn.disabled = true;
        emptyState.classList.add('d-none');
        container.classList.add('d-none');
        loading.classList.remove('d-none');

        const formData = new FormData();
        formData.append('resume_file', fileInput.files[0]);
        formData.append('job_description', jdInput.value);

        try {
            const resp = await fetch('/api/v1/evaluation/resume-pdf', {
                method: 'POST',
                body: formData
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                let errorMsg = `Server returned HTTP ${resp.status}`;
                if (typeof errData.detail === 'string') {
                    errorMsg = errData.detail;
                } else if (Array.isArray(errData.detail)) {
                    errorMsg = errData.detail.map(d => d.msg || d.message || JSON.stringify(d)).join(', ');
                } else if (errData.detail && typeof errData.detail === 'object') {
                    errorMsg = JSON.stringify(errData.detail);
                }
                throw new Error(errorMsg);
            }

            const data = await resp.json();
            container.innerHTML = buildEvaluationCardHTML(data);
            container.classList.remove('d-none');
            showToast('Candidate evaluation completed successfully!', 'success');

            // Update stats counter
            const counter = document.getElementById('metricTotalEvals');
            if (counter) counter.innerText = parseInt(counter.innerText || 0) + 1;

        } catch (err) {
            emptyState.classList.remove('d-none');
            showToast('Evaluation failed: ' + err.message, 'danger');
        } finally {
            loading.classList.add('d-none');
            btn.disabled = false;
        }
    });
}

// 2. Portfolio Screener Form Submission
const portfolioForm = document.getElementById('portfolioScreenForm');
if (portfolioForm) {
    portfolioForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const urlInput = document.getElementById('portfolioUrl');
        const directTextInput = document.getElementById('portfolioDirectText');
        const jdInput = document.getElementById('portfolioJdText');
        const btn = document.getElementById('screenPortfolioBtn');
        const emptyState = document.getElementById('portfolioEmptyState');
        const loading = document.getElementById('portfolioLoading');
        const container = document.getElementById('portfolioResultContainer');

        const urlVal = (urlInput?.value || '').trim();
        const textVal = (directTextInput?.value || '').trim();

        if (!urlVal && !textVal) {
            showToast('Please provide a website URL or paste candidate text directly.', 'warning');
            return;
        }

        btn.disabled = true;
        emptyState.classList.add('d-none');
        container.classList.add('d-none');
        loading.classList.remove('d-none');

        const formData = new FormData();
        if (urlVal) formData.append('portfolio_url', urlVal);
        if (textVal) formData.append('portfolio_text', textVal);
        formData.append('job_description', jdInput.value);

        try {
            const resp = await fetch('/api/v1/evaluation/portfolio-website', {
                method: 'POST',
                body: formData
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                let errorMsg = `Server returned HTTP ${resp.status}`;
                if (typeof errData.detail === 'string') {
                    errorMsg = errData.detail;
                } else if (Array.isArray(errData.detail)) {
                    errorMsg = errData.detail.map(d => d.msg || d.message || JSON.stringify(d)).join(', ');
                } else if (errData.detail && typeof errData.detail === 'object') {
                    errorMsg = JSON.stringify(errData.detail);
                }
                throw new Error(errorMsg);
            }

            const data = await resp.json();
            container.innerHTML = buildEvaluationCardHTML(data);
            container.classList.remove('d-none');
            showToast('Portfolio evaluation completed!', 'success');
        } catch (err) {
            emptyState.classList.remove('d-none');
            const msg = err.message || '';
            showToast(msg, 'danger');

            // If scraping failed due to client-side SPA or minimal text, auto-open the direct text box
            if (msg.includes('SPA') || msg.includes('readable text') || msg.includes('403')) {
                const collapseEl = document.getElementById('directTextCollapse');
                if (collapseEl && !collapseEl.classList.contains('show')) {
                    bootstrap.Collapse.getOrCreateInstance(collapseEl).show();
                    directTextInput?.focus();
                    showToast('Tip: This website is a JavaScript SPA. Paste candidate text directly above to evaluate!', 'info');
                }
            }
        } finally {
            loading.classList.add('d-none');
            btn.disabled = false;
        }
    });
}

// 3. LinkedIn X-Ray Sourcing Form Submission (Client-Side Widget & Direct Search)
const xrayForm = document.getElementById('xraySearchForm');
if (xrayForm) {
    xrayForm.addEventListener('submit', (e) => {
        e.preventDefault();
        if (typeof window.runWidgetSearch === 'function') {
            window.runWidgetSearch();
        } else {
            const googleBtn = document.getElementById('directGoogleSearchBtn');
            if (googleBtn && googleBtn.href) {
                window.open(googleBtn.href, '_blank');
            }
        }
    });
}

// 4. Footer AI Provider Status Synchronization
function updateFooterBadge(elementId, status, providerLabel) {
    const badge = document.getElementById(elementId);
    if (!badge) return;

    const icon = badge.querySelector('.bi-circle-fill');

    badge.classList.remove(
        'bg-success-subtle', 'text-success', 'border-success-subtle',
        'bg-danger-subtle', 'text-danger', 'border-danger-subtle',
        'bg-secondary-subtle', 'text-secondary'
    );
    if (icon) {
        icon.classList.remove('text-success', 'text-danger', 'text-secondary', 'opacity-50');
    }

    const isValid = status === 'valid' || status === true;
    const isInvalid = status === 'invalid';

    if (isValid) {
        badge.classList.add('bg-success-subtle', 'text-success', 'border', 'border-success-subtle');
        if (icon) icon.classList.add('text-success');
        badge.setAttribute('title', `${providerLabel} (Found & Valid)`);
    } else if (isInvalid) {
        badge.classList.add('bg-danger-subtle', 'text-danger', 'border', 'border-danger-subtle');
        if (icon) icon.classList.add('text-danger');
        badge.setAttribute('title', `${providerLabel} (Invalid Key)`);
    } else {
        badge.classList.add('bg-secondary-subtle', 'text-secondary', 'border');
        if (icon) icon.classList.add('text-secondary', 'opacity-50');
        badge.setAttribute('title', `${providerLabel} (Not Configured)`);
    }
}

async function syncFooterProviderStatus() {
    // 1. Read cached validation status from localStorage if present
    let localStatus = {};
    try {
        const cachedStr = localStorage.getItem('kayatix_ai_status');
        if (cachedStr) {
            localStatus = JSON.parse(cachedStr);
        }
    } catch (_) {}

    // 2. Fetch live settings status to sync with active DB
    try {
        const res = await fetch('/api/v1/settings');
        if (res.ok) {
            const settings = await res.json();
            const health = settings.provider_health || {};

            // If a key is NOT configured in DB/settings, it is strictly unconfigured
            const geminiStatus = !settings.gemini_api_key_configured
                ? 'unconfigured'
                : (localStatus.gemini || health.gemini || 'unconfigured');

            const groqStatus = !settings.groq_api_key_configured
                ? 'unconfigured'
                : (localStatus.groq || health.groq || 'unconfigured');

            const ollamaStatus = !settings.ollama_api_key_configured
                ? 'unconfigured'
                : (localStatus.ollama || health.ollama || 'unconfigured');

            updateFooterBadge('footerBadgeGemini', geminiStatus, 'Priority 1: Gemini 2.5 Flash');
            updateFooterBadge('footerBadgeGroq', groqStatus, 'Priority 2: Groq Llama 3.3 70B');
            updateFooterBadge('footerBadgeOllama', ollamaStatus, 'Priority 3: Ollama Cloud Fallback');
            return;
        }
    } catch (_) {}

    // Fallback to localStatus if API was unreachable
    if (localStatus.gemini) updateFooterBadge('footerBadgeGemini', localStatus.gemini, 'Priority 1: Gemini 2.5 Flash');
    if (localStatus.groq) updateFooterBadge('footerBadgeGroq', localStatus.groq, 'Priority 2: Groq Llama 3.3 70B');
    if (localStatus.ollama) updateFooterBadge('footerBadgeOllama', localStatus.ollama, 'Priority 3: Ollama Cloud Fallback');
}

window.updateFooterBadge = updateFooterBadge;
window.syncFooterProviderStatus = syncFooterProviderStatus;

document.addEventListener('DOMContentLoaded', () => {
    syncFooterProviderStatus();
});
