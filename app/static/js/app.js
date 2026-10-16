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
    if (p.includes('openrouter')) {
        return `<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle font-monospace"><i class="bi bi-cpu-fill me-1"></i>${provider}</span>`;
    }
    return `<span class="badge bg-secondary-subtle text-secondary border font-monospace">${provider}</span>`;
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

    return `
        <div class="card border-0 shadow-sm rounded-4 overflow-hidden mb-3">
            <div class="card-header border-bottom p-3 d-flex justify-content-between align-items-center">
                <div>
                    <h5 class="fw-bold mb-0 text-body-emphasis">${res.candidate_name || "Candidate Evaluation"}</h5>
                    <div class="d-flex align-items-center gap-2 small text-muted mt-1">
                        <span><i class="bi bi-briefcase me-1"></i> ${res.estimated_years_experience} YOE</span>
                        <span>&bull;</span>
                        <span>Provider: ${formatProviderBadge(provider)}</span>
                        <span>&bull;</span>
                        <span>${isCached ? '<span class="badge bg-success-subtle text-success"><i class="bi bi-check2"></i> Cache Hit</span>' : '<span class="badge bg-primary-subtle text-primary">Live Evaluated</span>'}</span>
                    </div>
                </div>
                <div>${scoreBadge}</div>
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
                        <div class="card border-0 shadow-sm rounded-3 mb-3 p-3 bg-body-tertiary">
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
            const errStr = (err.message || '');
            const errLower = errStr.toLowerCase();
            const dorkQuery = `site:linkedin.com/in/ "${payload.job_title}" AND "${payload.location}" AND ${payload.required_skills.map(s => `"${s}"`).join(' AND ')}`;
            const googleSearchUrl = 'https://www.google.com/search?q=' + encodeURIComponent(dorkQuery);
            const linkedinKeywords = [payload.job_title, payload.location, ...payload.required_skills.slice(0, 3)].join(' ');
            const linkedinSearchUrl = 'https://www.linkedin.com/search/results/people/?keywords=' + encodeURIComponent(linkedinKeywords);

            let headerTitle = "Google Cloud Sourcing Notice";
            let explanation = "";

            if (errLower.includes('does not have the access') || errLower.includes('permission_denied') || errLower.includes('restricted') || errLower.includes('closed')) {
                headerTitle = "Google Closed Custom Search JSON API for New Projects";
                explanation = `
                    <p class="small text-muted mb-2">
                        Google Cloud has permanently <strong>restricted and deprecated programmatic access</strong> to the legacy Custom Search JSON API (<code>customsearch.googleapis.com</code>) for all newly created Google Cloud projects.
                    </p>
                    <div class="p-2 bg-body-tertiary rounded text-danger small font-monospace mb-3 border">
                        403 Forbidden: "This project does not have the access to Custom Search JSON API."
                    </div>
                    <p class="small text-muted mb-3">
                        Even with the API enabled in Google Cloud Console, Google blocks automated in-app JSON calls for new accounts.
                        <br>
                        <strong class="text-success"><i class="bi bi-check-circle-fill me-1"></i> Good news: You do NOT need any API key to source candidates!</strong> Use our 1-click zero-setup alternatives below:
                    </p>
                `;
            } else if (errLower.includes('credentials') || errLower.includes('not configured')) {
                headerTitle = "Google Cloud API Key Not Configured";
                explanation = `
                    <p class="small text-muted mb-3">
                        Google Cloud API credentials are not configured in Settings.
                        <br>
                        <strong>You do NOT need Google Cloud Console to source candidates!</strong> Choose one of the 1-click zero-setup options below:
                    </p>
                `;
            } else {
                headerTitle = "Sourcing Engine Notice";
                explanation = `
                    <p class="small text-danger mb-2">${escapeHtml(errStr)}</p>
                    <p class="small text-muted mb-3">
                        You can immediately source candidates using our direct 1-click search or the browser-embedded CSE widget:
                    </p>
                `;
            }

            list.innerHTML = `
                <div class="alert alert-warning border border-warning-subtle rounded-4 p-4 shadow-sm">
                    <div class="d-flex align-items-center gap-2 mb-2">
                        <i class="bi bi-shield-exclamation text-warning fs-4"></i>
                        <h5 class="fw-bold mb-0 text-dark">${headerTitle}</h5>
                    </div>
                    ${explanation}
                    <div class="d-flex flex-wrap gap-2 mb-3">
                        <a href="${googleSearchUrl}" target="_blank" class="btn btn-primary btn-sm fw-semibold d-flex align-items-center gap-2">
                            <i class="bi bi-google"></i>
                            <span>Open 1-Click Search on Google (0 Setup)</span>
                            <i class="bi bi-box-arrow-up-right small"></i>
                        </a>
                        <button type="button" class="btn btn-outline-success btn-sm fw-semibold d-flex align-items-center gap-1" onclick="switchToCSEWidget()">
                            <i class="bi bi-window me-1"></i> Use Free CSE Widget (No Key Needed)
                        </button>
                        <a href="${linkedinSearchUrl}" target="_blank" class="btn btn-outline-secondary btn-sm fw-semibold d-flex align-items-center gap-2">
                            <i class="bi bi-linkedin text-primary"></i>
                            <span>Open in LinkedIn Search</span>
                            <i class="bi bi-box-arrow-up-right small"></i>
                        </a>
                    </div>
                    <div class="small text-secondary border-top pt-2 mt-2 d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <span class="text-truncate max-w-400">Query: <code class="small">${escapeHtml(dorkQuery)}</code></span>
                        <a href="/documentation/05-linkedin-xray-sourcing" class="text-decoration-none small text-primary">
                            <i class="bi bi-book me-1"></i> Read Sourcing Docs
                        </a>
                    </div>
                </div>
            `;
            list.classList.remove('d-none');
            showToast('Google API restricted. Please use 1-Click Google Search or CSE Widget below!', 'warning');
        } finally {
            loading.classList.add('d-none');
            btn.disabled = false;
        }
    });
}
