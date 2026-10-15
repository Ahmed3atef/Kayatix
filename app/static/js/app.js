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

// Render Evaluation Scorecard Card
function buildEvaluationCardHTML(apiData) {
    const res = apiData.analysis;
    const isCached = apiData.cached;
    const provider = apiData.provider_used;

    let scoreBadge = '';
    if (res.match_percentage >= 80) {
        scoreBadge = `<span class="badge bg-success fs-5 px-3 py-2 rounded-pill"><i class="bi bi-check-circle-fill me-1"></i> ${res.match_percentage}% Strong Fit</span>`;
    } else if (res.match_percentage >= 60) {
        scoreBadge = `<span class="badge bg-warning text-dark fs-5 px-3 py-2 rounded-pill"><i class="bi bi-exclamation-circle-fill me-1"></i> ${res.match_percentage}% Moderate Fit</span>`;
    } else {
        scoreBadge = `<span class="badge bg-danger fs-5 px-3 py-2 rounded-pill"><i class="bi bi-x-circle-fill me-1"></i> ${res.match_percentage}% Low Fit</span>`;
    }

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
                <div class="accordion-body bg-light small">
                    <p class="mb-2 fw-semibold text-dark">${q.question}</p>
                    <div class="mb-2"><strong>Tested Area:</strong> <span class="badge bg-secondary-subtle text-secondary">${q.target_area}</span></div>
                    <div class="mb-3"><strong>Expected Signals:</strong> <div class="p-2 bg-white rounded border">${q.expected_answer_criteria}</div></div>
                    <button class="btn btn-sm btn-outline-secondary" onclick="copyToClipboard('${q.question.replace(/'/g, "\\'")}', 'Question copied!')">
                        <i class="bi bi-clipboard"></i> Copy Question
                    </button>
                </div>
            </div>
        </div>
    `).join('') || '<div class="text-muted small">No questions generated.</div>';

    return `
        <div class="card border-0 shadow-sm rounded-4 overflow-hidden mb-3">
            <div class="card-header bg-white border-bottom p-3 d-flex justify-content-between align-items-center">
                <div>
                    <h5 class="fw-bold mb-0 text-dark">${res.candidate_name || "Candidate Evaluation"}</h5>
                    <div class="d-flex align-items-center gap-2 small text-muted mt-1">
                        <span><i class="bi bi-briefcase me-1"></i> ${res.estimated_years_experience} YOE</span>
                        <span>&bull;</span>
                        <span>Provider: <span class="badge bg-secondary-subtle text-secondary font-monospace">${provider}</span></span>
                        <span>&bull;</span>
                        <span>${isCached ? '<span class="badge bg-success-subtle text-success"><i class="bi bi-check2"></i> Cache Hit</span>' : '<span class="badge bg-primary-subtle text-primary">Live Evaluated</span>'}</span>
                    </div>
                </div>
                <div>${scoreBadge}</div>
            </div>
            <div class="card-body p-3">
                <div class="mb-3">
                    <h6 class="fw-bold text-uppercase text-secondary small mb-1">Executive Summary</h6>
                    <div class="p-3 bg-light rounded-3 border small text-dark">${res.executive_summary}</div>
                </div>

                <div class="row g-3 mb-3">
                    <div class="col-md-6">
                        <div class="p-3 border rounded-3 bg-light h-100">
                            <h6 class="fw-bold text-success mb-2 small"><i class="bi bi-check-circle"></i> Matched Skills</h6>
                            <div>${matchedSkills}</div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="p-3 border rounded-3 bg-light h-100">
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
                throw new Error(errData.detail || `Server returned HTTP ${resp.status}`);
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
        const jdInput = document.getElementById('portfolioJdText');
        const btn = document.getElementById('screenPortfolioBtn');
        const emptyState = document.getElementById('portfolioEmptyState');
        const loading = document.getElementById('portfolioLoading');
        const container = document.getElementById('portfolioResultContainer');

        btn.disabled = true;
        emptyState.classList.add('d-none');
        container.classList.add('d-none');
        loading.classList.remove('d-none');

        const formData = new FormData();
        formData.append('portfolio_url', urlInput.value);
        formData.append('job_description', jdInput.value);

        try {
            const resp = await fetch('/api/v1/evaluation/portfolio-website', {
                method: 'POST',
                body: formData
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || `Server returned HTTP ${resp.status}`);
            }

            const data = await resp.json();
            container.innerHTML = buildEvaluationCardHTML(data);
            container.classList.remove('d-none');
            showToast('Portfolio evaluation completed!', 'success');
        } catch (err) {
            emptyState.classList.remove('d-none');
            showToast('Portfolio evaluation failed: ' + err.message, 'danger');
        } finally {
            loading.classList.add('d-none');
            btn.disabled = false;
        }
    });
}

// 3. LinkedIn X-Ray Sourcing Form Submission
const xrayForm = document.getElementById('xraySearchForm');
if (xrayForm) {
    xrayForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const titleInput = document.getElementById('xrayJobTitle');
        const skillsInput = document.getElementById('xraySkills');
        const locInput = document.getElementById('xrayLocation');
        const maxInput = document.getElementById('xrayMaxResults');
        const btn = document.getElementById('searchXrayBtn');
        const emptyState = document.getElementById('xrayEmptyState');
        const loading = document.getElementById('xrayLoading');
        const list = document.getElementById('xrayResultsList');

        const skills = skillsInput.value.split(',').map(s => s.trim()).filter(s => s.length > 0);
        if (!skills.length) {
            showToast('Please specify at least one skill.', 'warning');
            return;
        }

        btn.disabled = true;
        emptyState.classList.add('d-none');
        list.classList.add('d-none');
        loading.classList.remove('d-none');

        const payload = {
            job_title: titleInput.value.trim(),
            required_skills: skills,
            location: locInput.value.trim(),
            max_results: parseInt(maxInput.value) || 5
        };

        try {
            const resp = await fetch('/api/v1/sourcing/linkedin-xray', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || `Server returned HTTP ${resp.status}`);
            }

            const profiles = await resp.json();
            if (!profiles || profiles.length === 0) {
                list.innerHTML = '<div class="alert alert-info">No profiles matched your search parameters. Try broadening your location or skills.</div>';
            } else {
                let html = `<div class="d-flex justify-content-between align-items-center mb-3"><h6 class="fw-bold mb-0">Discovered ${profiles.length} Public Profiles:</h6></div>`;
                profiles.forEach(p => {
                    const outreachText = `Hi there! I came across your profile regarding your experience as ${payload.job_title} and your background in ${payload.required_skills.slice(0, 2).join(' & ')}. We have an exciting opportunity that matches your skills. Would you be open to connecting?`;
                    html += `
                        <div class="card border-0 shadow-sm rounded-3 mb-3 p-3 bg-light">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h6 class="fw-bold mb-1 text-primary">${p.full_title}</h6>
                                    <a href="${p.linkedin_url}" target="_blank" class="small text-muted text-decoration-none d-inline-block mb-2">
                                        <i class="bi bi-box-arrow-up-right"></i> ${p.linkedin_url}
                                    </a>
                                </div>
                                <span class="badge bg-primary-subtle text-primary border"><i class="bi bi-linkedin"></i> Public</span>
                            </div>
                            <p class="small text-secondary mb-3">${p.snippet}</p>
                            <div>
                                <button class="btn btn-sm btn-outline-primary" onclick="copyToClipboard('${outreachText.replace(/'/g, "\\'")}', 'Outreach template copied!')">
                                    <i class="bi bi-chat-text"></i> Copy Outreach Template
                                </button>
                            </div>
                        </div>
                    `;
                });
                list.innerHTML = html;
            }
            list.classList.remove('d-none');
            showToast(`Found ${profiles.length} LinkedIn candidate profiles!`, 'success');
        } catch (err) {
            emptyState.classList.remove('d-none');
            showToast('X-Ray search error: ' + err.message, 'danger');
        } finally {
            loading.classList.add('d-none');
            btn.disabled = false;
        }
    });
}
