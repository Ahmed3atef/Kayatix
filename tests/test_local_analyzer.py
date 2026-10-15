import pytest
from app.services.local_analyzer import LocalResumeAnalyzer, local_analyzer


def test_dynamic_extraction_marketing_role():
    """Verify non-tech extraction works dynamically without any hardcoded tech taxonomies."""
    jd = """
    Job Title: Senior Marketing Director
    Requirements:
    • 7+ years of experience in Brand Strategy and Content Marketing.
    • Proven track record with Search Engine Optimization (SEO) and Google Analytics.
    • Hands-on expertise in HubSpot, Demand Generation, and Campaign ROI optimization.
    • A/B Testing, Customer Retention, and KPI Tracking.
    """
    candidate_cv = """
    Sarah Jenkins
    Email: sarah.jenkins@growthmarketing.io
    Professional Experience:
    Marketing Strategist (Jan 2018 - Present)
    - Spearheaded enterprise brand strategy generating $4.2M in annual recurring revenue.
    - Led content marketing and SEO campaigns boosting organic traffic by 180%.
    - Configured HubSpot automated nurturing sequences for 80k leads.
    """
    result = local_analyzer.evaluate(candidate_cv, jd)

    assert result["candidate_name"] == "Sarah Jenkins"
    assert "Brand Strategy" in result["matched_skills"]
    assert "Content Marketing" in result["matched_skills"]
    assert "SEO" in result["matched_skills"]
    assert "HubSpot" in result["matched_skills"]
    assert "Demand Generation" in result["missing_critical_skills"]
    assert "KPI Tracking" in result["missing_critical_skills"] or "Kpi Tracking" in result["missing_critical_skills"]
    assert result["estimated_years_experience"] >= 5.0
    assert len(result["detected_projects_and_impact"]) >= 2
    assert any("4.2M" in p for p in result["detected_projects_and_impact"])


def test_dynamic_extraction_finance_role():
    """Verify financial analysis competencies match correctly via smart stemming and phrase search."""
    jd = """
    Position: Senior Financial Analyst
    Qualifications:
    • Financial Modeling and DCF Valuation.
    • GAAP Compliance and Variance Analysis.
    • Bloomberg Terminal and Account Reconciliation.
    """
    candidate_cv = """
    David Miller, CPA
    david.miller@financecorp.com
    Experience:
    Financial Analyst (2019 - 2023)
    - Built comprehensive financial models and conducted DCF valuation for M&A deals.
    - Ensured full compliance with GAAP and performed monthly variance analysis across $80M portfolio.
    - Automated reporting workflows cutting close cycle by 4 days.
    """
    result = local_analyzer.evaluate(candidate_cv, jd)

    assert result["candidate_name"] == "David Miller"
    assert "Financial Modeling" in result["matched_skills"]
    assert "DCF Valuation" in result["matched_skills"]
    assert "GAAP Compliance" in result["matched_skills"]
    assert "Variance Analysis" in result["matched_skills"]
    assert "Bloomberg Terminal" in result["missing_critical_skills"]
    assert "Account Reconciliation" in result["missing_critical_skills"]
    assert result["match_percentage"] >= 50


def test_dynamic_extraction_healthcare_role():
    """Verify healthcare and clinical competencies match dynamically."""
    jd = """
    Role: Critical Care Nurse Specialist
    Qualifications:
    • Direct Patient Care and Clinical Triage in acute environments.
    • BLS/ACLS and CPR Certification required.
    • EHR/EMR documentation and HIPAA Compliance.
    • Medication Administration.
    """
    candidate_cv = """
    Elena Rostova, RN
    elena.rostova@medcenter.org
    Experience:
    Staff Nurse (2018 - 2023)
    - Provided direct patient care to 35+ critical patients weekly in ICU.
    - Certified in BLS/ACLS and CPR with distinction.
    - Managed EHR/EMR patient charts maintaining 100% HIPAA compliance.
    """
    result = local_analyzer.evaluate(candidate_cv, jd)

    assert result["candidate_name"] == "Elena Rostova"
    assert "Direct Patient Care" in result["matched_skills"]
    assert "BLS/ACLS" in result["matched_skills"]
    assert "CPR Certification" in result["matched_skills"]
    assert "EHR/EMR Documentation" in result["matched_skills"]
    assert "HIPAA Compliance" in result["matched_skills"]
    assert "Medication Administration" in result["missing_critical_skills"]
    assert result["match_percentage"] >= 60


def test_interval_union_true_yoe_and_gap_detection():
    """Test interval union merging overlapping job dates and flagging transition gaps > 6 months."""
    analyzer = LocalResumeAnalyzer()

    # Two overlapping jobs: 2019 to 2021 and 2020 to 2022 (should be 4 years, not 3 + 3 = 6)
    overlapping_text = """
    Experience:
    Software Consultant (Jan 2019 - Dec 2021)
    Technical Advisor (Jan 2020 - Dec 2022)
    """
    yoe, gaps = analyzer.calculate_years_experience(overlapping_text)
    assert 3.8 <= yoe <= 4.2
    assert len(gaps) == 0

    # Career gap between 2017 and 2020 (3 years unexplained gap)
    gap_text = """
    Experience:
    Junior Associate (Jan 2015 - Dec 2017)
    Senior Associate (Jan 2021 - Dec 2023)
    """
    yoe_gap, detected_gaps = analyzer.calculate_years_experience(gap_text)
    assert 5.5 <= yoe_gap <= 6.5
    assert len(detected_gaps) >= 1
    assert "Transition gap" in detected_gaps[0]


def test_domain_agnostic_impact_extraction():
    """Test quantified impact bullet extraction across sales, marketing, operations, and tech."""
    analyzer = LocalResumeAnalyzer()
    text = """
    • Spearheaded digital advertising campaign generating $3.5M in qualified pipeline.
    • Managed a team of 18 clinical specialists across three regional hospitals.
    • Just a regular bullet point without metrics or action verbs.
    • Reduced cloud infrastructure operational expenditure by 34% through automated scaling.
    • Another plain sentence with no numbers.
    """
    impacts = analyzer.extract_quantified_impact(text)
    assert len(impacts) == 3
    assert any("$3.5M" in imp for imp in impacts)
    assert any("team of 18" in imp for imp in impacts)
    assert any("34%" in imp for imp in impacts)


def test_regex_skill_special_symbols_and_boundaries():
    """Verify regular expression matching handles C#, C++, .NET, and word boundary isolation."""
    analyzer = LocalResumeAnalyzer()

    # Candidate with C# and .NET
    csharp_cv = "Senior Software Engineer. Stack: C#, ASP.NET Core, Microsoft Azure, SQL Server."
    assert analyzer.search_skill("c#", csharp_cv) is True
    assert analyzer.search_skill("csharp", csharp_cv) is True
    assert analyzer.search_skill(".net", csharp_cv) is True
    assert analyzer.search_skill("c++", csharp_cv) is False
    assert analyzer.search_skill("python", csharp_cv) is False

    # Candidate with C++ only
    cpp_cv = "Systems Programmer. Expert in C++20, Linux, CMake, and low-latency networking."
    assert analyzer.search_skill("c++", cpp_cv) is True
    assert analyzer.search_skill("c#", cpp_cv) is False

    # Candidate with Java (ensure Java does NOT match JavaScript)
    java_cv = "Backend Developer with Java Spring Boot experience."
    assert analyzer.search_skill("java", java_cv) is True
    assert analyzer.search_skill("javascript", java_cv) is False

    # Candidate with JavaScript (ensure JavaScript does NOT match Java requirement)
    js_cv = "Frontend Engineer specialized in JavaScript and React."
    assert analyzer.search_skill("javascript", js_cv) is True
    assert analyzer.search_skill("java", js_cv) is False


def test_regex_skill_compound_phrase_matching():
    """Verify compound JD requirements match via regex against candidate resume/portfolio text."""
    analyzer = LocalResumeAnalyzer()

    candidate_text = """
    Ahmed Atef
    Backend Developer
    Fabrica DEV
    Core Technologies: Python 3.11, FastAPI, Django, PostgreSQL, Docker, Redis, Celery, CI/CD, Git
    Projects:
    - FastAPI Blog API: High performance blogging microservice with async SQLAlchemy.
    - Kartpool: Backend microservices architecture with Redis caching and Docker deployment.
    """

    # Direct skills
    assert analyzer.match_requirement("FastAPI", candidate_text) is True
    assert analyzer.match_requirement("Python", candidate_text) is True
    assert analyzer.match_requirement("Docker", candidate_text) is True
    assert analyzer.match_requirement("CI/CD", candidate_text) is True

    # Compound JD phrases
    assert analyzer.match_requirement("Building Production Backends with Python", candidate_text) is True
    assert analyzer.match_requirement("Docker Containerization", candidate_text) is True
    assert analyzer.match_requirement("PostgreSQL Schema Design", candidate_text) is True
    assert analyzer.match_requirement("Experience in Redis Caching", candidate_text) is True

    # Missing skills must NOT match
    assert analyzer.match_requirement("C#", candidate_text) is False
    assert analyzer.match_requirement("Kubernetes Cluster Administration", candidate_text) is False
    assert analyzer.match_requirement("Salesforce CRM", candidate_text) is False


def test_regex_skill_explicit_custom_pattern():
    """Verify user or caller can pass custom regular expressions directly."""
    analyzer = LocalResumeAnalyzer()
    text = "Implemented caching layer using Redis and in-memory key-value stores."

    # Raw regex pattern
    assert analyzer.search_skill(r"\b(redis|memcached)\b", text) is True
    assert analyzer.search_skill(r"\b(kafka|rabbitmq)\b", text) is False


def test_regex_find_and_extract_skills_in_portfolio():
    """Verify find_skills_in_text and extract_skills detect skills using regular expressions."""
    analyzer = LocalResumeAnalyzer()
    portfolio_text = "Ahmed Atef. Backend Developer. Python, FastAPI, Django, PostgreSQL, Docker, Redis, Git."

    found = analyzer.find_skills_in_text(portfolio_text)
    assert "Python" in found
    assert "FastAPI" in found
    assert "PostgreSQL" in found
    assert "Docker" in found
    assert "Redis" in found

    extracted = analyzer.extract_skills(portfolio_text)
    assert "python" in extracted
    assert "fastapi" in extracted
    assert "docker" in extracted

