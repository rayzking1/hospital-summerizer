import React, { useState } from 'react';

// URL към бекенда (при локално тестване или Render)
const API_BASE_URL = "https://medisummarize-api.onrender.com";
 

export default function App() {
  // Състояние за автентификация
  const [token, setToken] = useState(null);
  const [doctor, setDoctor] = useState(null);

  // Форма за вход
  const [uin, setUin] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');

  // Форма за епикриза
  const [clinicalData, setClinicalData] = useState('');
  const [summary, setSummary] = useState('');
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [genError, setGenError] = useState('');

  // 1. Функция за Логин с УИН
    const handleGenerate = async () => {
    setError('');
    setSummary('');
    setLoading(true);

    try {
      // Взимаме УИН-а от обекта doctor, от уин state-а или ползваме резервния УИН
      const currentUin = doctor?.uin || uin || "1000000000";

      const res = await fetch(`${API_BASE_URL}/api/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uin: String(currentUin),
          clinical_data: clinicalData,
          model_name: 'gemini-2.5-flash'
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Грешка при генериране на епикризата');
      }

      setSummary(data.summary || data.result || JSON.stringify(data));
    } catch (err) {
      setError(err.message || 'Възникна непредвидена грешка');
    } finally {
      setLoading(false);
    }
  };


  // 2. Функция за генериране на Епикриза
    const handleGenerate = async () => {
    setError('');
    setSummary('');
    setLoading(true);

    try {
      // Взимаме УИН-а от обекта doctor, от уин state-а или ползваме резервния УИН
      const currentUin = doctor?.uin || uin || "1000000000";

      const res = await fetch(`${API_BASE_URL}/api/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          uin: String(currentUin),
          clinical_data: clinicalData,
          model_name: 'gemini-2.5-flash'
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Грешка при генериране на епикризата');
      }

      setSummary(data.summary || data.result || JSON.stringify(data));
    } catch (err) {
      setError(err.message || 'Възникна непредвидена грешка');
    } finally {
      setLoading(false);
    }
  };


  // -------------------------------------------------------------
  // ЕКРАН 1: ВХОД В СИСТЕМАТА (УИН & Парола)
  // -------------------------------------------------------------
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

  // -------------------------------------------------------------
  // ЕКРАН 2: РАБОТНО ТАБЛО (Dashboard)
  // -------------------------------------------------------------
  return (
    <div style={styles.dashboard}>
      {/* Горен панел / Навигация */}
      <header style={styles.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '28px' }}>🏥</span>
          <h3 style={{ margin: 0, color: '#0f172a' }}>MediSummarize Pro</h3>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '14px', color: '#334155' }}>
            👨‍⚕️ <strong>{doctor.name}</strong> ({doctor.specialty})
          </span>
          <button onClick={() => setToken(null)} style={styles.btnSecondary}>
            Изход
          </button>
        </div>
      </header>

      {/* Основна работна площ */}
      <main style={styles.mainContent}>
        {/* Лява колона: Входящи данни */}
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
            disabled={loading}
            style={{
              ...styles.btnPrimary,
              marginTop: '16px',
              backgroundColor: loading ? '#94a3b8' : '#0084c7',
              width: '100%',
              cursor: loading ? 'wait' : 'pointer'
            }}
          >
            {loading ? '⏳ Генериране на епикриза...' : '🚀 Генерирай Епикриза'}
          </button>

          {genError && <div style={styles.errorBanner}>{genError}</div>}
        </div>

        {/* Дясна колона: Генериран резултат & Одит */}
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
            rows="12"
            readOnly
            placeholder="Тук ще се появи готовата структурирана епикриза..."
            value={summary}
            style={{ ...styles.textarea, backgroundColor: '#f8fafc' }}
          />
        </div>
      </main>
    </div>
  );
}

// -------------------------------------------------------------
// СТИЛОВЕ (Медицинска цветова гама: Clean Medical Blue)
// -------------------------------------------------------------
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
};
