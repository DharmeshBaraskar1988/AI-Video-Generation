import { Img } from "remotion";
import logo from "../../../data/brand/logo.svg";

/** The brand logo (data/brand/logo.svg) on a white card so it reads on any background. */
export const Logo: React.FC<{ height: number; card?: boolean }> = ({ height, card = true }) => (
  <div
    style={{
      display: "inline-flex",
      background: card ? "white" : "transparent",
      borderRadius: height * 0.18,
      padding: card ? height * 0.12 : 0,
      boxShadow: card ? "0 12px 40px rgba(0,0,0,0.18)" : "none",
    }}
  >
    <Img src={logo} style={{ height, display: "block" }} />
  </div>
);
