document.addEventListener('DOMContentLoaded', () => {
  const htmlEl = document.documentElement;
  const yearEl = document.getElementById('year');
  if (yearEl) {
    yearEl.textContent = new Date().getFullYear().toString();
  }

  const navToggle = document.querySelector('.nav-toggle');
  const navList = document.querySelector('.nav-list');

  if (navToggle && navList) {
    navToggle.addEventListener('click', () => {
      navList.classList.toggle('is-open');
    });

    navList.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        navList.classList.remove('is-open');
      });
    });
  }

  const navLinks = document.querySelectorAll('.nav-list a[href^="#"]');
  navLinks.forEach((link) => {
    link.addEventListener('click', (e) => {
      const targetId = link.getAttribute('href');
      if (!targetId || !targetId.startsWith('#')) return;

      const target = document.querySelector(targetId);
      if (!target) return;

      e.preventDefault();

      const header = document.querySelector('.header');
      const headerHeight = header ? header.getBoundingClientRect().height : 0;
      const targetTop = target.getBoundingClientRect().top + window.scrollY;

      window.scrollTo({
        top: targetTop - headerHeight - 8,
        behavior: 'smooth',
      });
    });
  });

  const sections = document.querySelectorAll('section[id]');
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const id = entry.target.getAttribute('id');
        if (!id) return;
        navLinks.forEach((link) => {
          const href = link.getAttribute('href');
          if (!href) return;
          link.classList.toggle('is-active', href.slice(1) === id);
        });
      });
    },
    {
      rootMargin: '-60% 0px -35% 0px',
      threshold: 0,
    }
  );

  sections.forEach((section) => observer.observe(section));

  const translations = {
    ko: {
      'nav.about': '자기소개',
      'nav.experience': '경력·경험',
      'nav.projects': '수행 이력',
      'hero.tag': 'ERP · Strategy · Internal Control',
      'hero.title': '백소영 Portfolio',
      'hero.sub':
        'ERP, 전략기획, 거버넌스·내부통제를 연결하는 비즈니스-시스템 연계형 전문가입니다.',
      'hero.ctaProjects': '프로젝트 보러가기',
      'hero.ctaAbout': '자기소개 보기',
      'about.title': '자기소개',
      'about.body':
        'ERP 구축/운영, 전략기획, 내부통제 및 인증 대응 경험을 바탕으로 비즈니스와 기술을 연결하는 실무형 IT 기획·운영 담당자입니다.',
      'about.basic': '기본 정보',
      'about.nameLabel': '이름',
      'about.nameValue': '백소영 (SoYoung Back)',
      'about.positionLabel': '포지션',
      'about.skillLabel': '핵심역량',
      'about.skillValue': '프로세스·화면 설계 / DB 설계 / 거버넌스·내부통제',
      'about.degreeLabel': '학위',
      'about.emailLabel': '이메일',
      'exp.title': '경력 · 경험',
      'exp.sub': 'ERP, 전략기획, 내부통제 및 거버넌스까지의 경험을 요약합니다.',
      'exp.emro.meta': '2024.11 ~ 현재 · 사업기획',
      'exp.emro.desc':
        'SOC 2 Type 1·2 인증 및 보안·규정 기반 거버넌스 체계 정비를 수행하며 서비스 운영 조직의 내부통제 수준을 고도화하고 있습니다.',
      'exp.dplanex.meta': '2022.08 ~ 2024.11 · 사업기획',
      'exp.dplanex.desc':
        '그룹사 데이터 레이크 사업 추진 및 매출 실현에 기여하며 데이터 기반 사업 모델 수립과 운영 체계 정비를 지원했습니다.',
      'exp.dts.meta': '2021.11 ~ 2022.08 · IT 전략기획',
      'exp.dts.desc':
        '관계사 대상 IT 전략기획을 수행하고 데이터 전문법인 설립 추진을 지원하며 IT·데이터 거버넌스 체계 수립에 참여했습니다.',
      'exp.douzone.meta': '2015.11 ~ 2021.11 · ERP 구축',
      'exp.douzone.desc':
        '20개 이상의 ERP 구축 프로젝트를 수행하며 요구사항 분석, 프로세스 설계, 화면·DB 설계, 운영 안정화까지 전 주기를 경험했습니다.',
      'projects.title': '수행 이력',
      'projects.sub': '거버넌스·내부통제, ERP, PMO 경험이 녹아 있는 주요 수행 내역입니다.',
      'proj.soc.title': 'SOC 인증',
      'proj.soc.desc': '인증 기획/총괄 및 유관부서 협업으로 전 통제항목 통과',
      'proj.erp.title': 'ERP 구축 및 업무 프로세스 고도화',
      'proj.erp.desc': '요구사항 분석부터 설계/커뮤니케이션/운영 안정화까지',
      'proj.pmo.title': '전략 기획 및 디지털 전환',
      'proj.pmo.desc': 'CRM 도입/내재화 및 데이터 거버넌스 체계 구축',
      'proj.ai.title': 'AI 자동화 멀티 에이전트 워크플로',
      'proj.ai.desc': '매뉴얼 제작을 자동화하는 4계층 멀티 에이전트 체계 설계·구축',
      'footer.top': '위로 올라가기',
    },
    en: {
      'nav.about': 'About',
      'nav.experience': 'Experience',
      'nav.projects': 'Projects',
      'hero.tag': 'ERP · Strategy · Internal Control',
      'hero.title': 'SoYoung Back Portfolio',
      'hero.sub':
        'A business–system bridging expert connecting ERP, strategic planning, governance and internal control.',
      'hero.ctaProjects': 'View projects',
      'hero.ctaAbout': 'View profile',
      'about.title': 'About',
      'about.body':
        'IT planner/operator with hands-on experience in ERP implementation & operation, strategic planning, internal control and certification response, bridging business and technology.',
      'about.basic': 'Profile',
      'about.nameLabel': 'Name',
      'about.nameValue': 'SoYoung Back',
      'about.positionLabel': 'Position',
      'about.skillLabel': 'Core Skills',
      'about.skillValue': 'Process/Screen Design · DB Design · Governance & Internal Control',
      'about.degreeLabel': 'Degree',
      'about.emailLabel': 'Email',
      'exp.title': 'Experience',
      'exp.sub': 'Summary of experience across ERP, strategic planning, internal control and governance.',
      'exp.emro.meta': '2024.11 – Present · Business Planning',
      'exp.emro.desc':
        'Leading SOC 2 Type 1·2 certification and security/compliance-based governance, advancing internal controls across the service operations organization.',
      'exp.dplanex.meta': '2022.08 – 2024.11 · Business Planning',
      'exp.dplanex.desc':
        'Drove the group data-lake business and contributed to revenue realization, supporting data-driven business models and operating frameworks.',
      'exp.dts.meta': '2021.11 – 2022.08 · IT Strategy',
      'exp.dts.desc':
        'Led IT strategy for affiliates, supported the launch of a dedicated data company, and helped establish IT & data governance.',
      'exp.douzone.meta': '2015.11 – 2021.11 · ERP Implementation',
      'exp.douzone.desc':
        'Delivered 20+ ERP implementation projects across the full cycle — requirements analysis, process design, screen/DB design, and operational stabilization.',
      'projects.title': 'Project Highlights',
      'projects.sub':
        'Key engagements that capture my experience in governance/internal control, ERP and PMO.',
      'proj.soc.title': 'SOC Certification',
      'proj.soc.desc': 'Planned & led certification; passed all controls via cross-team collaboration',
      'proj.erp.title': 'ERP Implementation & Process Improvement',
      'proj.erp.desc': 'From requirements analysis to design, communication, and stabilization',
      'proj.pmo.title': 'Strategic Planning & Digital Transformation',
      'proj.pmo.desc': 'CRM adoption/embedding and data-governance build-out',
      'proj.ai.title': 'AI Automation Multi-Agent Workflow',
      'proj.ai.desc': 'Designed & built a 4-layer multi-agent system to automate manual production',
      'footer.top': 'Back to top',
    },
  };

  let currentLang = 'ko';

  function applyLanguage(lang) {
    const dict = translations[lang];
    if (!dict) return;

    currentLang = lang === 'en' ? 'en' : 'ko';

    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      const value = dict[key];
      if (!value) return;
      el.textContent = value;
    });

    htmlEl.lang = currentLang;

    const langButtons = document.querySelectorAll('.lang-btn');
    langButtons.forEach((btn) => {
      btn.classList.toggle('is-active', btn.dataset.lang === lang);
    });

    window.localStorage.setItem('lang', lang);
  }

  document.querySelectorAll('.lang-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const lang = btn.dataset.lang || 'ko';
      applyLanguage(lang);
      // re-render the JS-driven project detail in the new language
      const selected = document.querySelector('.project-tab.is-selected');
      const selectedId = selected ? selected.dataset.project : 'soc';
      if (selectedId) selectProjectTab(selectedId);
    });
  });

  const storedLang = window.localStorage.getItem('lang');
  if (storedLang === 'en' || storedLang === 'ko') {
    applyLanguage(storedLang);
  }

  const projectTabs = Array.from(document.querySelectorAll('.project-tab[data-project]'));
  const detailKicker = document.getElementById('project-detail-kicker');
  const detailTitle = document.getElementById('project-detail-title');
  const detailSub = document.getElementById('project-detail-sub');
  const detailBody = document.getElementById('project-detail-body');

  const erpRows = [
    {
      period: '2021.06 - 2022.01',
      client: '에이치이엠파마',
      clientEn: 'HEM Pharmaco',
      role: 'PL',
      industry: '바이오/제조',
      industryEn: 'Bio · Mfg',
      desc: '프로젝트 원가/배부, 용역매출원가 계산 및 손익 관리 구축',
      descEn: 'Built project costing/allocation, service COGS calculation, and P&L management',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2020.04 - 2021.01',
      client: '벽산',
      clientEn: 'Byucksan',
      role: 'PL',
      industry: '건자재/제조',
      industryEn: 'Building Mat. · Mfg',
      desc: '관리회계(사업계획, 표준/제조원가, 수익성분석) 구축',
      descEn: 'Built managerial accounting: business planning, standard/manufacturing cost, profitability analysis',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2019.11 - 2020.04',
      client: '지엔엠라이프',
      clientEn: 'GNM Life',
      role: 'PL',
      industry: '유통',
      industryEn: 'Distribution',
      desc: '외주구매 및 원가 구축, 사방넷 인터페이스 연동',
      descEn: 'Outsourced purchasing & costing; Sabangnet interface integration',
      tags: ['원가관리', '구매/물류', 'PL'],
    },
    {
      period: '2019.05 - 2020.01',
      client: '쿠도커뮤니케이션',
      clientEn: 'Kudo Communication',
      role: 'PL',
      industry: 'IT',
      industryEn: 'IT',
      desc: 'PMS(프로젝트 관리 시스템) 및 원가 시스템 구축',
      descEn: 'Built a PMS (project management system) and costing system',
      tags: ['원가관리', 'PM', 'PL'],
    },
    {
      period: '2018.11 - 2019.11',
      client: '엑사이엔씨',
      clientEn: 'EXA E&C',
      role: 'PL',
      industry: '전자/제조',
      industryEn: 'Electronics · Mfg',
      desc: '인천공장 전체 담당: 원가/영업/구매/생산/무역/기준정보 구축',
      descEn: 'Full ownership of the Incheon plant: cost, sales, purchasing, production, trade, master data',
      tags: ['원가관리', '구매/물류', 'PL'],
    },
    {
      period: '2019.08 - 2019.08',
      client: '와이디생명과학',
      clientEn: 'YD Life Science',
      role: 'PM',
      industry: '바이오',
      industryEn: 'Bio',
      desc: '물류 고도화 데이터 VIEW 생성 및 제공',
      descEn: 'Logistics enhancement — created and delivered data views',
      tags: ['구매/물류', 'PM'],
    },
    {
      period: '2018.12 - 2019.07',
      client: '새턴바스',
      clientEn: 'Saturn Bath',
      role: 'PL',
      industry: '제조',
      industryEn: 'Manufacturing',
      desc: '실제원가 구축 지원 및 시스템 안정화',
      descEn: 'Supported actual-costing build and system stabilization',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2018.12 - 2019.06',
      client: '선일케미칼',
      clientEn: 'Sunil Chemical',
      role: 'PL',
      industry: '화학/제조',
      industryEn: 'Chemical · Mfg',
      desc: '표준/실제원가 및 한계이익 관리 체계 구축',
      descEn: 'Built standard/actual costing and contribution-margin management',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2018.08 - 2019.02',
      client: '지피클럽',
      clientEn: 'GP Club',
      role: 'PL',
      industry: '제조',
      industryEn: 'Manufacturing',
      desc: 'EC모듈, 구매자재 및 수입모듈 프로세스 구축',
      descEn: 'Built EC module, purchasing/materials, and import module processes',
      tags: ['구매/물류', 'PL'],
    },
    {
      period: '2018.11 - 2018.12',
      client: '니콘이미징코리아',
      clientEn: 'Nikon Imaging Korea',
      role: 'PM',
      industry: '전자/제조',
      industryEn: 'Electronics · Mfg',
      desc: 'ERP - 그룹웨어(GW) 연동 고도화',
      descEn: 'ERP–groupware (GW) integration enhancement',
      tags: ['PM'],
    },
    {
      period: '2018.07 - 2018.12',
      client: '포스코터미날',
      clientEn: 'POSCO Terminal',
      role: 'PL',
      industry: '물류/운송',
      industryEn: 'Logistics · Transport',
      desc: '구매자재 구축, 자재표준화 및 선석/도면관리 I/F 개발',
      descEn: 'Purchasing/materials build, material standardization, berth/drawing management interfaces',
      tags: ['구매/물류', 'PL'],
    },
    {
      period: '2017.04 - 2018.09',
      client: '하츠',
      clientEn: 'Haatz',
      role: 'PL',
      industry: '가전/제조',
      industryEn: 'Home Appliance · Mfg',
      desc: '통합원가/결산관리 구축, 렌탈관리 시스템(PL보조) 구축',
      descEn: 'Built integrated costing/closing management and a rental management system (PL support)',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2018.04 - 2018.07',
      client: '한국코와',
      clientEn: 'Kowa Korea',
      role: 'PM',
      industry: '제약/유통',
      industryEn: 'Pharma · Distribution',
      desc: '영업모듈 고도화 (2차 프로젝트)',
      descEn: 'Sales module enhancement (phase 2)',
      tags: ['PM'],
    },
    {
      period: '2017.03 - 2018.04',
      client: '야놀자',
      clientEn: 'Yanolja',
      role: 'PL',
      industry: 'IT/플랫폼',
      industryEn: 'IT · Platform',
      desc: 'EC모듈 및 구매자재 모듈 구축',
      descEn: 'Built EC module and purchasing/materials module',
      tags: ['구매/물류', 'PL'],
    },
    {
      period: '2017.05 - 2017.06',
      client: '한국코와',
      clientEn: 'Kowa Korea',
      role: 'PM',
      industry: '제약/유통',
      industryEn: 'Pharma · Distribution',
      desc: 'PG사 결제 시스템 변경 및 최적화',
      descEn: 'Payment-gateway system change and optimization',
      tags: ['PM'],
    },
    {
      period: '2015.12 - 2017.02',
      client: '코스콤',
      clientEn: 'Koscom',
      role: 'QA/PL',
      industry: '금융IT',
      industryEn: 'Fintech',
      desc: '품질 관리(QA) 및 BT(Back-up Tape) 모듈 구축',
      descEn: 'Quality assurance (QA) and BT (back-up tape) module build',
      tags: ['PM', 'PL'],
    },
  ];

  const projectDetailById = {
    soc: {
      kicker: 'Tab 01',
      title: {
        ko: 'SOC Type 1·2 인증 기획 및 총괄',
        en: 'SOC Type 1·2 Certification — Planning & Lead',
      },
      sub: {
        ko: '유관부서 및 계열회사 협업으로 전 통제항목 통과 및 인증서 발급 완료',
        en: 'Passed all control items and obtained certification through cross-team and affiliate collaboration',
      },
      bullets: {
        ko: [
          'SOC 2 Type 1, Type 2 인증 기획 및 총괄',
          '유관부서/계열회사와 협업하여 전 통제항목 통과 및 인증서 발급 완료',
          '글로벌 SaaS 서비스 플랫폼 런칭과 함께 북미 고객 대상 운영 회의 리드',
          '서비스 신뢰성 및 확장성 확보',
        ],
        en: [
          'Planned and led SOC 2 Type 1 and Type 2 certification',
          'Passed all control items and completed certificate issuance with related teams/affiliates',
          'Led operations meetings for North American customers alongside the global SaaS platform launch',
          'Secured service reliability and scalability',
        ],
      },
      links: [
        {
          href: 'https://www.datanews.co.kr/news/article.html?no=142864',
          label: {
            ko: '관련 기사: 엠로 SRM SaaS 솔루션 SOC2 타입2 획득 (DataNews)',
            en: 'Article: EMRO SRM SaaS solution obtains SOC 2 Type 2 (DataNews)',
          },
        },
      ],
    },
    erp: {
      kicker: 'Tab 02',
      title: {
        ko: 'ERP 구축 및 업무 프로세스 고도화',
        en: 'ERP Implementation & Process Improvement',
      },
      sub: {
        ko: '다양한 산업군의 ERP 구축/고도화 프로젝트를 End-to-End로 수행',
        en: 'Delivered end-to-end ERP implementation/enhancement projects across diverse industries',
      },
    },
    pmo: {
      kicker: 'Tab 03',
      title: {
        ko: '전략 기획 및 디지털 전환',
        en: 'Strategic Planning & Digital Transformation',
      },
      sub: {
        ko: 'CRM 도입/내재화 및 그룹 데이터 거버넌스 체계 구축',
        en: 'CRM adoption/embedding and group-wide data governance',
      },
      bullets: {
        ko: [
          'Salesforce(CRM) 도입 및 성공적 내재화',
          '현업 요구사항 분석 및 Salesforce 솔루션 도입 검토/선정 총괄',
          '데이터 분석 전문 법인 설립 및 데이터 거버넌스 구축',
          '그룹 내 흩어진 데이터를 통합 관리하고 분석하기 위한 데이터 분석 전문 자회사(디플래닉스) 설립 기획 지원',
          '금융·비금융 데이터를 아우르는 그룹 통합 데이터 거버넌스 체계 구축 및 매출화',
        ],
        en: [
          'Adopted and successfully embedded Salesforce (CRM)',
          'Led business requirements analysis and Salesforce solution review/selection',
          'Established a specialized data-analytics company and data governance',
          'Supported planning of a dedicated data-analytics subsidiary (DPLANEX) to integrate and analyze scattered group data',
          'Built and monetized a group-wide integrated data governance framework spanning financial and non-financial data',
        ],
      },
      links: [
        {
          href: 'https://magazine.hankyung.com/business/article/202304278076b',
          label: {
            ko: '관련 기사: 교보생명, 5개 자회사 데이터 한곳에…디지털 전환 포석 (매거진한경)',
            en: 'Article: Kyobo Life consolidates data from 5 subsidiaries — a digital-transformation move (Magazine Hankyung)',
          },
        },
      ],
    },
    ai: {
      kicker: 'Tab 04',
      title: {
        ko: '매뉴얼 제작 자동화 멀티 에이전트 워크플로',
        en: 'Multi-Agent Workflow for Manual-Production Automation',
      },
      sub: {
        ko: '판단 기준·실행 절차·역할·워크플로를 4개 계층으로 설계한 멀티 에이전트 자동화 체계 구축',
        en: 'Built a multi-agent automation system structured in four layers: standards, procedures, roles, and workflows',
      },
      bullets: {
        ko: [
          '지식층(판단 기준): 캡처 규격·소스 검증·체크리스트를 표준 가이드(v2)로 확정 → AI가 판단 기준을 스스로 참조',
          '능력층(실행 절차): 공용 캡처 엔진 + 모듈별 설정 구조의 캡처 스킬 등 재사용 가능한 실행 절차 정의',
          '역할층(작업 주체): writer·reviewer 에이전트로 작성·검수 역할 분리',
          '워크플로층(일의 순서): manual-new / manual-update 커맨드로 전체 작업 순서 표준화',
          '결과: /manual-update Item Master 한 줄이면 에이전트가 가이드를 읽고 스킬을 꺼내 정해진 순서대로 매뉴얼 작업 수행',
          '개별 에이전트가 아니라 업무 표준·역할·프로세스를 갖춘 "작은 자동화 부서"를 구축 — 사람 개입 없는 무인 실행(비감독 자동화)의 기반',
        ],
        en: [
          'Knowledge layer (standards): finalized capture specs, source verification, and checklists into a v2 guide — so the AI references its own basis for judgment',
          'Capability layer (procedures): defined reusable skills such as a shared capture engine with per-module configuration',
          'Role layer (who does the work): separate writer and reviewer agents for drafting and review',
          'Workflow layer (order of work): standardized the end-to-end sequence via manual-new / manual-update commands',
          'Result: a single command — /manual-update Item Master — has agents read the guide, pull the right skills, and execute the work in order',
          'Not individual agents but a small self-running "automation department" with its own standards, roles, and process — a foundation for unattended (unsupervised) execution',
        ],
      },
    },
  };

  // resolve a value that may be a plain string or a { ko, en } object
  function L(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return value[currentLang] ?? value.ko ?? '';
    }
    return value;
  }

  // UI strings for the JS-rendered ERP table
  const erpUi = {
    summary: { ko: '* 총 20건 이상의 프로젝트 수행', en: '* 20+ projects delivered in total' },
    roleLabel: { ko: '역할', en: 'Role' },
    industryLabel: { ko: '산업군', en: 'Industry' },
    all: { ko: '전체', en: 'All' },
    thPeriod: { ko: '기간', en: 'Period' },
    thClient: { ko: '고객사 / 산업군', en: 'Client / Industry' },
    thRole: { ko: '역할', en: 'Role' },
    thDesc: { ko: '주요 수행 내역', en: 'Key Deliverables' },
  };

  // display labels for the single-token industry filter chips
  // (data-industry stays Korean so the existing filter logic is unchanged)
  const industryLabels = {
    '바이오': 'Bio',
    '제조': 'Mfg',
    '건자재': 'Building Mat.',
    '유통': 'Distribution',
    IT: 'IT',
    '화학': 'Chemical',
    '물류': 'Logistics',
    '운송': 'Transport',
    '가전': 'Appliance',
    '제약': 'Pharma',
    '플랫폼': 'Platform',
    '금융': 'Finance',
  };

  function escapeHtml(unsafe) {
    return String(unsafe)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function renderErpDetail() {
    if (detailKicker) detailKicker.textContent = projectDetailById.erp.kicker;
    if (detailTitle) {
      detailTitle.textContent = L(projectDetailById.erp.title);
      detailTitle.classList.add('is-erp');
    }
    if (detailSub) {
      detailSub.textContent = L(projectDetailById.erp.sub);
      detailSub.classList.add('is-erp');
    }
    if (!detailBody) return;

    const industries = [
      '바이오',
      '제조',
      '건자재',
      '유통',
      'IT',
      '화학',
      '물류',
      '운송',
      '가전',
      '제약',
      '플랫폼',
      '금융',
    ];

    const rowsHtml = erpRows
      .map((row, index) => {
        const tagsAttr = row.tags.join(',');
        const zebra = index % 2 === 0 ? 'erp-row-even' : 'erp-row-odd';
        const clientName = currentLang === 'en' && row.clientEn ? row.clientEn : row.client;
        const industryText = currentLang === 'en' && row.industryEn ? row.industryEn : row.industry;
        const descText = currentLang === 'en' && row.descEn ? row.descEn : row.desc;
        return `
          <tr class="erp-row ${zebra}" data-tags="${escapeHtml(tagsAttr)}" data-role="${escapeHtml(
           row.role
         )}" data-industry="${escapeHtml(row.industry)}">
            <td>${escapeHtml(row.period)}</td>
            <td>
              <div class="erp-client">
                <span class="erp-client-name">${escapeHtml(clientName)}</span>
                <span class="erp-client-industry">${escapeHtml(industryText)}</span>
              </div>
            </td>
            <td>${escapeHtml(row.role)}</td>
            <td>${escapeHtml(descText)}</td>
          </tr>
        `;
      })
      .join('');

    const allLabel = L(erpUi.all);

    detailBody.innerHTML = `
      <p class="erp-summary-text">${escapeHtml(L(erpUi.summary))}</p>
      <div class="erp-filters">
        <div class="erp-filter-group">
          <span class="erp-filter-label">${escapeHtml(L(erpUi.roleLabel))}</span>
          <div class="erp-filter-chips" role="tablist">
            <button type="button" class="chip is-active" data-role="전체">${escapeHtml(allLabel)}</button>
            <button type="button" class="chip" data-role="PM">PM</button>
            <button type="button" class="chip" data-role="PL">PL</button>
          </div>
        </div>
        <div class="erp-filter-group">
          <span class="erp-filter-label">${escapeHtml(L(erpUi.industryLabel))}</span>
          <div class="erp-filter-chips">
            <button type="button" class="chip is-active" data-industry="전체">${escapeHtml(allLabel)}</button>
            ${industries
              .map((ind) => {
                const label = currentLang === 'en' && industryLabels[ind] ? industryLabels[ind] : ind;
                return `<button type="button" class="chip" data-industry="${escapeHtml(ind)}">${escapeHtml(label)}</button>`;
              })
              .join('')}
          </div>
        </div>
      </div>
      <div class="erp-table-wrapper">
        <table class="erp-table">
          <thead>
            <tr>
              <th>${escapeHtml(L(erpUi.thPeriod))}</th>
              <th>${escapeHtml(L(erpUi.thClient))}</th>
              <th>${escapeHtml(L(erpUi.thRole))}</th>
              <th>${escapeHtml(L(erpUi.thDesc))}</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    `;

    setupErpFilters();
  }

  function renderProjectDetail(projectId) {
    if (projectId === 'erp') {
      renderErpDetail();
      return;
    }

    const data = projectDetailById[projectId];
    if (!data) return;

    if (detailKicker) detailKicker.textContent = data.kicker;
    if (detailTitle) {
      detailTitle.textContent = L(data.title);
      detailTitle.classList.remove('is-erp');
    }
    if (detailSub) {
      detailSub.textContent = L(data.sub);
      detailSub.classList.remove('is-erp');
    }
    if (!detailBody) return;

    const bulletsHtml = (L(data.bullets) || [])
      .map((item) => `<li>${escapeHtml(item)}</li>`)
      .join('');

    const linksHtml = (data.links || [])
      .map(
        (link) =>
          `<a href="${escapeHtml(link.href)}" target="_blank" rel="noreferrer noopener">${escapeHtml(L(link.label))}</a>`
      )
      .join('');

    detailBody.innerHTML = `
      <ul class="project-detail-list">${bulletsHtml}</ul>
      ${linksHtml ? `<div class="project-detail-links">${linksHtml}</div>` : ''}
    `;
  }

  function setupErpFilters() {
    let selectedRole = '전체';
    let selectedIndustry = '전체';

    const roleButtons = Array.from(document.querySelectorAll('.chip[data-role]'));
    const industryButtons = Array.from(document.querySelectorAll('.chip[data-industry]'));
    const rows = Array.from(document.querySelectorAll('.erp-row'));

    function applyFilters() {
      rows.forEach((row) => {
        const rowRole = row.dataset.role || '';
        const rowIndustry = row.dataset.industry || '';

        const roleParts = rowRole.split('/').map((part) => part.trim()).filter(Boolean);
        const matchRole =
          selectedRole === '전체' || roleParts.includes(selectedRole) || rowRole === selectedRole;
        const matchIndustry =
          selectedIndustry === '전체' || rowIndustry.includes(selectedIndustry);

        const isVisible = matchRole && matchIndustry;
        row.style.display = isVisible ? '' : 'none';
      });
    }

    roleButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        selectedRole = btn.dataset.role || '전체';
        roleButtons.forEach((b) => b.classList.toggle('is-active', b === btn));
        applyFilters();
      });
    });

    industryButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        selectedIndustry = btn.dataset.industry || '전체';
        industryButtons.forEach((b) => b.classList.toggle('is-active', b === btn));
        applyFilters();
      });
    });

    applyFilters();
  }

  function selectProjectTab(nextId) {
    projectTabs.forEach((tab) => {
      const isSelected = tab.dataset.project === nextId;
      tab.classList.toggle('is-selected', isSelected);
      tab.setAttribute('aria-selected', isSelected ? 'true' : 'false');
    });
    renderProjectDetail(nextId);
  }

  if (projectTabs.length) {
    projectTabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const id = tab.dataset.project;
        if (!id) return;
        selectProjectTab(id);
      });
    });

    const initialId = projectTabs.find((t) => t.classList.contains('is-selected'))?.dataset.project || 'soc';
    selectProjectTab(initialId);
  }
});

