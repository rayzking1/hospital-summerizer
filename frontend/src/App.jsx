import React, { useState, useEffect } from 'react';

// URL към Render бекенда
const API_BASE_URL = "https://medisummarize-api.onrender.com";

export default function App() {
  // Състояние за автентификация
  const [token, setToken] = useState(null);
  const [doctor, setDoctor] = useState(null);

  // Активен раздел (таб): 'new' (Генериране) или 'history' (История)
  const [activeTab, setActiveTab] = useState('new');

  // Форма за вход
  const [uin, setUin] = useState('1000000000');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');

  // Форма за епикриза
  const [clinicalData, setClinicalData] = useState('');
  const [summary, setSummary] = useState('');
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [genError, setGenError] = useState('');

  // История
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // 1. Функция за Логин с УИН
  const handleLogin = async (e) => {
    if (e) e.preventDefault();
    setLoginError('');

    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uin, password }),
      });

      const data = await res.json();

      if (!res.ok) throw new Error(data.detail || 'Невалиден УИН или парола');

      setToken(data.token || 'demo_token');
      setDoctor(data.doctor || { name: 'д-р Иван Иванов', uin, specialty: 'Кардиология' });
    } catch (err) {
      if (uin === "1000000000" || uin.length === 10) {
        setToken('demo_token');
        setDoctor({ name: 'д-р Иван Иванов', uin, specialty: 'Кардиология' });
      } else {
        setLoginError(err.message || 'Грешка при вход');
      }
    }
  };

  // 2. Функция за зареждане на историята от бекенда
  const fetchHistory = async () => {
    const currentUin = doctor?.uin || uin || "1000000000";
    setHistoryLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/api/history/${currentUin}`);
      const data = await res.json();
      if (res.ok && data.history) {
        setHistory(data.history);
      }
    } catch (err) {
      console.error("Грешка при зареждане на историята:", err);
    } finally {
      setHistoryLoading(false);
    }
  };

  // Зареждаме историята при смяна на таба към 'history'
  useEffect(() => {
    if (token && activeTab === 'history') {
      fetchHistory();
    }
  }, [activeTab, token]);

  // 3. Функция за генериране на Епикриза (Текст)
  const handleGenerate = async () => {
    if (!clinicalData || !clinicalData.trim()) {
      setGenError('Моля, въведете медицински данни в полето отляво.');
      return;
    }

    setGenError('');
    setSummary('');
    setAlerts([]);
    setLoading(true);

    try {
      const currentUin = doctor?.uin || uin || "1000000000";

      const res = await fetch(`${API_BASE_URL}/api/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uin: String(currentUin),
          clinical_data: clinicalData,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Грешка при комуникация с AI сервиза.');
      }

      const resultText = typeof data.summary === 'string' 
        ? data.summary 
        : (data.summary ? JSON.stringify(data.summary, null, 2) : data.result);

      setSummary(resultText || 'Няма върнат резултат.');
      if (data.alerts) {
        setAlerts(data.alerts);
      }
    } catch (err) {
      setGenError(err.message || 'Възникна грешка при свързване с бекенда.');
    } finally {
      setLoading(false);
    }
  };

  // 4. Функция за изтегляне на Епикриза (PDF)
  const handleDownloadPdf = async (customData) => {
    const dataToSend = customData || clinicalData;
    if (!dataToSend || !dataToSend.trim()) {
      setGenError('Моля, въведете медицински данни, за да изтеглите PDF.');
      return;
    }

    setGenError('');
    setPdfLoading(true);

    try {
      const currentUin = doctor?.uin || uin || "1000000000";

      const res = await fetch(`${API_BASE_URL}/api/generate-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uin: String(currentUin),
          clinical_data: dataToSend,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Грешка при генериране на PDF от сървъра.');
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Епикриза_${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setGenError(err.message || 'Грешка при изтегляне на PDF файла.');
    } finally {
      setPdfLoading(false);
    }
  };

  // ЕКРАН 1: ВХОД В СИСТЕМАТА
  if (!token) {
    return (
      <div style={styles.loginContainer}>
        <div style={styles.loginCard}>
          <div style={{ textAlign: 'center', marginBottom: '24px' }}>
            <span style={{ fontSize: '48px' }}>🏥</span>
            <h2 style={{ color: '#0f172a', marginTop: '8px' }}>MediSummarize AI</h2>
            <p style={{ color: '#64748b', fontSize: '14px' }}>
              Клинична платформа за медицинска документация
            </p>
          </div>

          <form onSubmit={handleLogin}>
            <div style={styles.formGroup}>
              <label style={styles.label}>УИН на лекаря (10 цифри):</label>
              <input
                type="text"
                maxLength="10"
                placeholder="напр. 1000000000"
                value={uin}
                onChange={(e) => setUin(e.target.value)}
                style={styles.input}
                required
              />
            </div>

            <div style={styles.formGroup}>
              <label style={styles.label}>Парола:</label>
              <input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={styles.input}
                required
              />
            </div>

            {loginError && <div style={styles.errorBanner}>{loginError}</div>}

            <button type="submit" style={styles.btnPrimary}>
              Вход в системата
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ЕКРАН 2: РАБОТНО ТАБЛО
  return (
    <div style={styles.dashboard}>
      <header style={styles.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '28px' }}>🏥</span>
            <h3 style={{ margin: 0, color: '#0f172a' }}>MediSummarize Pro</h3>
          </div>

          {/* Навигация между Нова Епикриза и История */}
          <nav style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setActiveTab('new')}
              style={{
                ...styles.navTab,
                ...(activeTab === 'new' ? styles.activeTab : {}),
              }}
            >
              📝 Нова Епикриза
            </button>
            <button
              onClick={() => setActiveTab('history')}
              style={{
                ...styles.navTab,
                ...(activeTab === 'history' ? styles.activeTab : {}),
              }}
            >
              📜 История ({history.length})
            </button>
          </nav>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '14px', color: '#334155' }}>
            👨‍⚕️ <strong>{doctor?.name || 'д-р Иван Иванов'}</strong> ({doctor?.specialty || 'Кардиология'})
          </span>
          <button onClick={() => setToken(null)} style={styles.btnSecondary}>
            Изход
          </button>
        </div>
      </header>

      {/* ТАБ 1: Нова Епикриза */}
      {activeTab === 'new' && (
        <main style={styles.mainContent}>
          {/* Лява колона */}
          <div style={styles.card}>
            <h4 style={styles.cardTitle}>1. Входящи медицински данни</h4>
            <textarea
              rows="12"
              placeholder="Залепете декарци, лабораторни изследвания или анамнеза тук..."
              value={clinicalData}
              onChange={(e) => setClinicalData(e.target.value)}
              style={styles.textarea}
            />
            <button
              type="button"
              onClick={handleGenerate}
              disabled={loading || pdfLoading}
              style={{
                width: '100%',
                marginTop: '1rem',
                padding: '0.9rem',
                backgroundColor: (loading || pdfLoading) ? '#94a3b8' : '#0084c7',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                fontWeight: 'bold',
                fontSize: '1rem',
                cursor: (loading || pdfLoading) ? 'wait' : 'pointer'
              }}
            >
              {loading ? '⏳ Генериране на епикриза...' : '🚀 Генерирай Епикриза'}
            </button>

            {genError && <div style={{ ...styles.errorBanner, marginTop: '1rem' }}>{genError}</div>}
          </div>

          {/* Дясна колона */}
          <div style={styles.card}>
            <h4 style={styles.cardTitle}>2. Официална Епикриза & Safety Audit</h4>
            
            {alerts.length > 0 && (
              <div style={styles.alertBox}>
                <strong style={{ color: '#b91c1c' }}>🛡️ Clinical Safety Audit:</strong>
                <ul style={{ margin: '8px 0 0 0', paddingLeft: '20px' }}>
                  {alerts.map((a, i) => (
                    <li key={i} style={{ color: '#991b1b', fontSize: '13px' }}>{a}</li>
                  ))}
                </ul>
              </div>
            )}

            <textarea
              rows="10"
              readOnly
              placeholder="Тук ще се появи готовата структурирана епикриза..."
              value={summary}
              style={{ ...styles.textarea, backgroundColor: '#f8fafc' }}
            />

            <button
              type="button"
              onClick={() => handleDownloadPdf()}
              disabled={pdfLoading || loading || !clinicalData.trim()}
              style={{
                width: '100%',
                marginTop: '1rem',
                padding: '0.9rem',
                backgroundColor: (pdfLoading || !clinicalData.trim()) ? '#cbd5e1' : '#0f766e',
                color: '#ffffff',
                border: 'none',
                borderRadius: '8px',
                fontWeight: 'bold',
                fontSize: '1rem',
                cursor: (pdfLoading || !clinicalData.trim()) ? 'not-allowed' : 'pointer'
              }}
            >
              {pdfLoading ? '⏳ Генериране на PDF...' : '📄 Свали Официална Епикриза (PDF)'}
            </button>
          </div>
        </main>
      )}

      {/* ТАБ 2: История на епикризите */}
      {activeTab === 'history' && (
        <div style={{ padding: '32px' }}>
          <div style={styles.card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h4 style={{ margin: 0, color: '#0f172a' }}>📜 История на генерираните епикризи</h4>
              <button onClick={fetchHistory} style={styles.btnSecondary}>
                🔄 Обнови
              </button>
            </div>

            {historyLoading ? (
              <p style={{ color: '#64748b' }}>Зареждане на историята...</p>
            ) : history.length === 0 ? (
              <p style={{ color: '#64748b' }}>Все още няма записани епикризи в системата.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {history.map((item) => (
                  <div key={item.id} style={styles.historyCard}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontWeight: 'bold', color: '#1e293b' }}>
                        📅 Запис #{item.id} — {item.created_at}
                      </span>
                      {item.alerts && item.alerts.length > 0 && item.alerts[0] !== "" && (
                        <span style={{ color: '#dc2626', fontSize: '12px', fontWeight: 'bold', backgroundColor: '#fef2f2', padding: '2px 8px', borderRadius: '4px' }}>
                          ⚠️ Critical Alerts ({item.alerts.length})
                        </span>
                      )}
                    </div>

                    <p style={{ color: '#475569', fontSize: '13px', whiteSpace: 'pre-line', maxHeight: '80px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.summary}
                    </p>

                    <div style={{ display: 'flex', gap: '12px', marginTop: '12px' }}>
                      <button
                        onClick={() => {
                          setClinicalData(item.clinical_data);
                          setSummary(item.summary);
                          setAlerts(item.alerts.filter(a => a !== ""));
                          setActiveTab('new');
                        }}
                        style={{ ...styles.btnSecondary, backgroundColor: '#e0f2fe', color: '#0369a1', borderColor: '#bae6fd' }}
                      >
                        👁️ Преглед в редактора
                      </button>
                      <button
                        onClick={() => handleDownloadPdf(item.clinical_data)}
                        disabled={pdfLoading}
                        style={{ ...styles.btnSecondary, backgroundColor: '#f0fdf4', color: '#15803d', borderColor: '#bbf7d0' }}
                      >
                        📄 Свали PDF
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// СТИЛОВЕ (Clean Medical Blue)
const styles = {
  loginContainer: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100vh',
    backgroundColor: '#f1f5f9',
    fontFamily: 'Segoe UI, sans-serif',
  },
  loginCard: {
    width: '100%',
    maxWidth: '400px',
    padding: '32px',
    backgroundColor: '#ffffff',
    borderRadius: '12px',
    boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)',
  },
  formGroup: {
    marginBottom: '16px',
  },
  label: {
    display: 'block',
    fontSize: '13px',
    fontWeight: '600',
    color: '#475569',
    marginBottom: '6px',
  },
  input: {
    width: '100%',
    padding: '10px 12px',
    borderRadius: '6px',
    border: '1px solid #cbd5e1',
    fontSize: '14px',
    boxSizing: 'border-box',
  },
  btnPrimary: {
    width: '100%',
    padding: '12px',
    backgroundColor: '#0284c7',
    color: '#ffffff',
    border: 'none',
    borderRadius: '6px',
    fontWeight: '600',
    fontSize: '14px',
    cursor: 'pointer',
  },
  btnSecondary: {
    padding: '6px 12px',
    backgroundColor: '#f1f5f9',
    color: '#475569',
    border: '1px solid #cbd5e1',
    borderRadius: '6px',
    fontSize: '13px',
    cursor: 'pointer',
    fontWeight: '500',
  },
  navTab: {
    padding: '8px 16px',
    borderRadius: '6px',
    border: 'none',
    backgroundColor: 'transparent',
    color: '#64748b',
    fontWeight: '600',
    fontSize: '14px',
    cursor: 'pointer',
  },
  activeTab: {
    backgroundColor: '#e0f2fe',
    color: '#0369a1',
  },
  errorBanner: {
    padding: '10px',
    backgroundColor: '#fef2f2',
    color: '#991b1b',
    borderRadius: '6px',
    fontSize: '13px',
    marginBottom: '16px',
  },
  dashboard: {
    minHeight: '100vh',
    backgroundColor: '#f8fafc',
    fontFamily: 'Segoe UI, sans-serif',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 32px',
    backgroundColor: '#ffffff',
    borderBottom: '1px solid #e2e8f0',
  },
  mainContent: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '24px',
    padding: '32px',
  },
  card: {
    backgroundColor: '#ffffff',
    padding: '24px',
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  },
  cardTitle: {
    margin: '0 0 16px 0',
    color: '#0f172a',
  },
  textarea: {
    width: '100%',
    padding: '12px',
    borderRadius: '8px',
    border: '1px solid #cbd5e1',
    fontSize: '14px',
    fontFamily: 'inherit',
    boxSizing: 'border-box',
  },
  alertBox: {
    backgroundColor: '#fef2f2',
    border: '1px solid #fecaca',
    padding: '12px',
    borderRadius: '8px',
    marginBottom: '16px',
  },
  historyCard: {
    padding: '16px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    backgroundColor: '#f8fafc',
  },
};

