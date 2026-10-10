import { useMemo } from "react";
import { AbsoluteFill, Html5Audio, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Captions } from "./components/Captions";
import { Presenter } from "./components/Presenter";
import { Intro } from "./scenes/Intro";
import { KpiCards } from "./scenes/KpiCards";
import { alpha, defaultBrand, ThemeContext, type Theme } from "./theme/brand";
import { fontFor } from "./theme/fonts";
import type { VideoProps } from "./types";

export const SOCIAL_SECONDS = 15;
const INTRO_SECONDS = 3;

/**
 * 15-second social cut: the intro title card (music only), then the KPI scene with its own
 * narration and captions, taken from the same props as the full video.
 */
export const SocialCut: React.FC<VideoProps> = (props) => {
  const { fps, durationInFrames } = useVideoConfig();
  const frame = useCurrentFrame();
  const brand = props.brand ?? defaultBrand;
  const theme: Theme = useMemo(
    () => ({
      brand,
      c: brand.colors,
      lang: props.language,
      dir: props.direction,
      digits: props.digits ?? "western",
      font: fontFor(props.language),
      presenter: Boolean(props.presenter),
    }),
    [brand, props.language, props.direction, props.digits, props.presenter],
  );

  const intro = props.scenes.find((s) => s.type === "intro");
  const kpis = props.scenes.find((s) => s.type === "kpis") ?? props.scenes[1];
  const introFrames = INTRO_SECONDS * fps;
  const kpiStart = kpis.audioStart;
  const shift = INTRO_SECONDS - kpiStart;
  const words = useMemo(
    () =>
      props.words
        .filter((w) => w.start >= kpiStart && w.end <= kpiStart + SOCIAL_SECONDS - INTRO_SECONDS)
        .map((w) => ({ ...w, start: w.start + shift, end: w.end + shift })),
    [props.words, kpiStart, shift],
  );
  const audioSrc = props.audio.startsWith("http") ? props.audio : staticFile(props.audio);
  const fadeOut = interpolate(frame, [durationInFrames - 15, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <ThemeContext.Provider value={theme}>
      <AbsoluteFill
        lang={props.language}
        dir={props.direction}
        style={{ background: brand.colors.background, fontFamily: theme.font, opacity: fadeOut }}
      >
        <Sequence durationInFrames={introFrames} name="intro">
          {intro && <Intro data={intro.data} />}
        </Sequence>
        <Sequence from={introFrames} name="kpis">
          <Html5Audio src={audioSrc} trimBefore={Math.round(kpiStart * fps)} />
          <KpiCards data={kpis.data} />
        </Sequence>
        {props.presenter && (
          <Sequence from={introFrames} name="presenter">
            <Presenter words={words.map((w) => ({ ...w, start: w.start - INTRO_SECONDS, end: w.end - INTRO_SECONDS }))} look={props.presenter} />
          </Sequence>
        )}
        {props.captions && <Captions words={words} />}
        {props.demo && (
          <div
            style={{
              position: "absolute",
              bottom: 172,
              [props.presenter ? "insetInlineStart" : "insetInlineEnd"]: 24,
              padding: "8px 18px",
              borderRadius: 30,
              background: alpha(brand.colors.secondary, 0.92),
              color: "white",
              fontSize: 22,
              fontWeight: 600,
            }}
          >
            {props.language === "ar" ? "بيانات تجريبية" : "Demo data"}
          </div>
        )}
      </AbsoluteFill>
    </ThemeContext.Provider>
  );
};
