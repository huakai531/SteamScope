import Link from "next/link";
import { LandingEntry } from "@/components/landing-entry";
import { SystemStatus } from "@/components/system-status";
import { ProductPreview, JourneyPreview } from "@/components/product-preview";

export default function Home() {
  return (
    <div className="landing landing-v4">
      <a className="skip-link" href="#landing-main">
        Skip to content
      </a>
      <header className="landing-nav">
        <Link className="brand" href="/">
          SteamScope<span className="brand-dot">.</span>
        </Link>
        <nav aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#features">Features</a>
          <LandingEntry compact />
        </nav>
      </header>
      <main id="landing-main" tabIndex={-1}>
        <section className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-copy">
            <h1 id="landing-title">
              Find your people.
              <br />
              Through play.
            </h1>
            <p>
              Create your Steam player profile, discover shared games, and
              connect with your people.
            </p>
            <LandingEntry />
            <small>SteamScope never receives your Steam password.</small>
          </div>
          <ProductPreview />
        </section>
        <section
          id="how-it-works"
          className="landing-journey"
          aria-labelledby="journey-title"
        >
          <div className="journey-heading">
            <h2 id="journey-title">How it works</h2>
          </div>
          <div className="journey-grid" id="features">
            <article>
              <JourneyPreview kind="profile" />
              <h3>Your player profile</h3>
              <p>Your games, playtime and achievements.</p>
            </article>
            <article>
              <JourneyPreview kind="discover" />
              <h3>Find your people</h3>
              <p>Discover players through shared games.</p>
            </article>
            <article>
              <JourneyPreview kind="chat" />
              <h3>Connect and talk</h3>
              <p>Connect. Chat in real time.</p>
            </article>
          </div>
        </section>
      </main>
      <footer className="landing-footer">
        <div className="landing-footer-row">
          <Link className="brand" href="/">
            SteamScope<span className="brand-dot">.</span>
          </Link>
          <p>Not affiliated with or endorsed by Valve Corporation.</p>
        </div>
        <details className="landing-boundaries">
          <summary>Your privacy</summary>
          <p>
            You choose what players can see. Steam sign-in and importing games
            are separate actions. Chat is for accepted connections; you can
            block at any time.
          </p>
        </details>
        <details className="landing-health">
          <summary>Service status</summary>
          <SystemStatus />
        </details>
      </footer>
    </div>
  );
}
