import { useNavigate } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import hero from '../assets/hero-illustration.webp'
import './Landing.css'

export default function Landing() {
  const navigate = useNavigate()

  return (
    <div className="landing">
      <span className="landing-blob landing-blob--left" aria-hidden="true" />
      <span className="landing-blob landing-blob--right" aria-hidden="true" />

      <header className="landing-header">
        <a href="/" aria-label="Acadza home">
          <Logo />
        </a>
      </header>

      <main className="landing-main">
        <section className="landing-copy">
          <div className="brand-lockup">
            <span className="brand-acadza">ACADZA</span>
            <span className="brand-check">
              CHECK
              <svg className="brand-sparkle" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 2c.6 4.6 2.4 6.9 7 8-4.6 1.1-6.4 3.4-7 8-.6-4.6-2.4-6.9-7-8 4.6-1.1 6.4-3.4 7-8z" />
              </svg>
            </span>
          </div>
          <p className="brand-tagline">
            <span className="brand-tagline-under">
              Your question
              <svg className="brand-swoosh" viewBox="0 0 120 12" preserveAspectRatio="none" aria-hidden="true">
                <path d="M3 9 C 35 2, 80 1, 117 4" />
              </svg>
            </span>{' '}
            quality companion
          </p>

          <h1 className="landing-title">
            Check before
            <br />
            they <span className="landing-title-accent">learn.</span>
          </h1>

          <p className="landing-lede">
            AI-powered question verification for Acadza faculty. Find, verify and fix question errors—before they reach
            students.
          </p>

          <button className="cta" type="button" onClick={() => navigate('/dashboard')}>
            Check Questions
            <svg className="cta-arrow" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </button>
        </section>

        <figure className="landing-art">
          <img
            src={hero}
            alt="A smiling teacher holding a clipboard, with a checklist and a verified math card around her"
            width="1800"
            height="1596"
          />
        </figure>
      </main>
    </div>
  )
}
