import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="site-footer" role="contentinfo">
      <div className="site-footer-inner">
        <nav aria-label="Footer" className="site-footer-nav">
          <Link to="/about">About</Link>
          <Link to="/pricing">Pricing</Link>
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
          <a href="mailto:hello@campable.co">Contact</a>
        </nav>
        <p className="site-footer-meta">© {new Date().getFullYear()} Campable</p>
      </div>
    </footer>
  );
}

export default Footer;
