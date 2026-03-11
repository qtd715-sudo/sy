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
      'about.positionLabel': '포지션',
      'about.skillLabel': '핵심역량',
      'about.degreeLabel': '학위',
      'about.emailLabel': '이메일',
      'exp.title': '경력 · 경험',
      'exp.sub': 'ERP, 전략기획, 내부통제 및 거버넌스까지의 경험을 요약합니다.',
      'projects.title': '수행 이력',
      'projects.sub': '거버넌스·내부통제, ERP, PMO 경험이 녹아 있는 주요 수행 내역입니다.',
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
      'about.positionLabel': 'Position',
      'about.skillLabel': 'Core Skills',
      'about.degreeLabel': 'Degree',
      'about.emailLabel': 'Email',
      'exp.title': 'Experience',
      'exp.sub': 'Summary of experience across ERP, strategic planning, internal control and governance.',
      'projects.title': 'Project Highlights',
      'projects.sub':
        'Key engagements that capture my experience in governance/internal control, ERP and PMO.',
    },
  };

  function applyLanguage(lang) {
    const dict = translations[lang];
    if (!dict) return;

    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      const value = dict[key];
      if (!value) return;
      el.textContent = value;
    });

    htmlEl.lang = lang === 'en' ? 'en' : 'ko';

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
      role: 'PL',
      industry: '바이오/제조',
      desc: '프로젝트 원가/배부, 용역매출원가 계산 및 손익 관리 구축',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2020.04 - 2021.01',
      client: '벽산',
      role: 'PL',
      industry: '건자재/제조',
      desc: '관리회계(사업계획, 표준/제조원가, 수익성분석) 구축',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2019.11 - 2020.04',
      client: '지엔엠라이프',
      role: 'PL',
      industry: '유통',
      desc: '외주구매 및 원가 구축, 사방넷 인터페이스 연동',
      tags: ['원가관리', '구매/물류', 'PL'],
    },
    {
      period: '2019.05 - 2020.01',
      client: '쿠도커뮤니케이션',
      role: 'PL',
      industry: 'IT',
      desc: 'PMS(프로젝트 관리 시스템) 및 원가 시스템 구축',
      tags: ['원가관리', 'PM', 'PL'],
    },
    {
      period: '2018.11 - 2019.11',
      client: '엑사이엔씨',
      role: 'PL',
      industry: '전자/제조',
      desc: '인천공장 전체 담당: 원가/영업/구매/생산/무역/기준정보 구축',
      tags: ['원가관리', '구매/물류', 'PL'],
    },
    {
      period: '2019.08 - 2019.08',
      client: '와이디생명과학',
      role: 'PM',
      industry: '바이오',
      desc: '물류 고도화 데이터 VIEW 생성 및 제공',
      tags: ['구매/물류', 'PM'],
    },
    {
      period: '2018.12 - 2019.07',
      client: '새턴바스',
      role: 'PL',
      industry: '제조',
      desc: '실제원가 구축 지원 및 시스템 안정화',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2018.12 - 2019.06',
      client: '선일케미칼',
      role: 'PL',
      industry: '화학/제조',
      desc: '표준/실제원가 및 한계이익 관리 체계 구축',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2018.08 - 2019.02',
      client: '지피클럽',
      role: 'PL',
      industry: '제조',
      desc: 'EC모듈, 구매자재 및 수입모듈 프로세스 구축',
      tags: ['구매/물류', 'PL'],
    },
    {
      period: '2018.11 - 2018.12',
      client: '니콘이미징코리아',
      role: 'PM',
      industry: '전자/제조',
      desc: 'ERP - 그룹웨어(GW) 연동 고도화',
      tags: ['PM'],
    },
    {
      period: '2018.07 - 2018.12',
      client: '포스코터미날',
      role: 'PL',
      industry: '물류/운송',
      desc: '구매자재 구축, 자재표준화 및 선석/도면관리 I/F 개발',
      tags: ['구매/물류', 'PL'],
    },
    {
      period: '2017.04 - 2018.09',
      client: '하츠',
      role: 'PL',
      industry: '가전/제조',
      desc: '통합원가/결산관리 구축, 렌탈관리 시스템(PL보조) 구축',
      tags: ['원가관리', 'PL'],
    },
    {
      period: '2018.04 - 2018.07',
      client: '한국코와',
      role: 'PM',
      industry: '제약/유통',
      desc: '영업모듈 고도화 (2차 프로젝트)',
      tags: ['PM'],
    },
    {
      period: '2017.03 - 2018.04',
      client: '야놀자',
      role: 'PL',
      industry: 'IT/플랫폼',
      desc: 'EC모듈 및 구매자재 모듈 구축',
      tags: ['구매/물류', 'PL'],
    },
    {
      period: '2017.05 - 2017.06',
      client: '한국코와',
      role: 'PM',
      industry: '제약/유통',
      desc: 'PG사 결제 시스템 변경 및 최적화',
      tags: ['PM'],
    },
    {
      period: '2015.12 - 2017.02',
      client: '코스콤',
      role: 'QA/PL',
      industry: '금융IT',
      desc: '품질 관리(QA) 및 BT(Back-up Tape) 모듈 구축',
      tags: ['PM', 'PL'],
    },
  ];

  const projectDetailById = {
    soc: {
      kicker: 'Tab 01',
      title: 'SOC Type 1·2 인증 기획 및 총괄',
      sub: '유관부서 및 계열회사 협업으로 전 통제항목 통과 및 인증서 발급 완료',
      bullets: [
        'SOC 2 Type 1, Type 2 인증 기획 및 총괄',
        '유관부서/계열회사와 협업하여 전 통제항목 통과 및 인증서 발급 완료',
        '글로벌 SaaS 서비스 플랫폼 런칭과 함께 북미 고객 대상 운영 회의 리드',
        '서비스 신뢰성 및 확장성 확보',
      ],
      links: [
        {
          href: 'https://www.datanews.co.kr/news/article.html?no=142864',
          label: '관련 기사: 엠로 SRM SaaS 솔루션 SOC2 타입2 획득 (DataNews)',
        },
      ],
    },
    erp: {
      kicker: 'Tab 02',
      title: 'ERP 구축 및 업무 프로세스 고도화',
      sub: '다양한 산업군의 ERP 구축/고도화 프로젝트를 End-to-End로 수행',
    },
    pmo: {
      kicker: 'Tab 03',
      title: '전략 기획 및 디지털 전환',
      sub: 'CRM 도입/내재화 및 그룹 데이터 거버넌스 체계 구축',
      bullets: [
        'Salesforce(CRM) 도입 및 성공적 내재화',
        '현업 요구사항 분석 및 Salesforce 솔루션 도입 검토/선정 총괄',
        '데이터 분석 전문 법인 설립 및 데이터 거버넌스 구축',
        '그룹 내 흩어진 데이터를 통합 관리하고 분석하기 위한 데이터 분석 전문 자회사(디플래닉스) 설립 기획 지원',
        '금융·비금융 데이터를 아우르는 그룹 통합 데이터 거버넌스 체계 구축 및 매출화',
      ],
      links: [
        {
          href: 'https://magazine.hankyung.com/business/article/202304278076b',
          label: '관련 기사: 교보생명, 5개 자회사 데이터 한곳에…디지털 전환 포석 (매거진한경)',
        },
      ],
    },
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
      detailTitle.textContent = projectDetailById.erp.title;
      detailTitle.classList.add('is-erp');
    }
    if (detailSub) {
      detailSub.textContent = projectDetailById.erp.sub;
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
        return `
          <tr class="erp-row ${zebra}" data-tags="${escapeHtml(tagsAttr)}" data-role="${escapeHtml(
           row.role
         )}" data-industry="${escapeHtml(row.industry)}">
            <td>${escapeHtml(row.period)}</td>
            <td>
              <div class="erp-client">
                <span class="erp-client-name">${escapeHtml(row.client)}</span>
                <span class="erp-client-industry">${escapeHtml(row.industry)}</span>
              </div>
            </td>
            <td>${escapeHtml(row.role)}</td>
            <td>${escapeHtml(row.desc)}</td>
          </tr>
        `;
      })
      .join('');

    detailBody.innerHTML = `
      <p class="erp-summary-text">* 총 20건 이상의 프로젝트 수행</p>
      <div class="erp-filters">
        <div class="erp-filter-group">
          <span class="erp-filter-label">역할</span>
          <div class="erp-filter-chips" role="tablist">
            <button type="button" class="chip is-active" data-role="전체">전체</button>
            <button type="button" class="chip" data-role="PM">PM</button>
            <button type="button" class="chip" data-role="PL">PL</button>
          </div>
        </div>
        <div class="erp-filter-group">
          <span class="erp-filter-label">산업군</span>
          <div class="erp-filter-chips">
            <button type="button" class="chip is-active" data-industry="전체">전체</button>
            ${industries
              .map(
                (ind) =>
                  `<button type="button" class="chip" data-industry="${escapeHtml(ind)}">${escapeHtml(ind)}</button>`
              )
              .join('')}
          </div>
        </div>
      </div>
      <div class="erp-table-wrapper">
        <table class="erp-table">
          <thead>
            <tr>
              <th>기간</th>
              <th>고객사 / 산업군</th>
              <th>역할</th>
              <th>주요 수행 내역</th>
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
      detailTitle.textContent = data.title;
      detailTitle.classList.remove('is-erp');
    }
    if (detailSub) {
      detailSub.textContent = data.sub;
      detailSub.classList.remove('is-erp');
    }
    if (!detailBody) return;

    const bulletsHtml = (data.bullets || [])
      .map((item) => `<li>${escapeHtml(item)}</li>`)
      .join('');

    const linksHtml = (data.links || [])
      .map(
        (link) =>
          `<a href="${escapeHtml(link.href)}" target="_blank" rel="noreferrer noopener">${escapeHtml(link.label)}</a>`
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

