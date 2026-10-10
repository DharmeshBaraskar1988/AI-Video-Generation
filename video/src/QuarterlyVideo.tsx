import { useMemo } from "react";
import { AbsoluteFill, Html5Audio, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Captions } from "./components/Captions";
import { Presenter } from "./components/Presenter";
import { Drivers } from "./scenes/Drivers";
import { Intro } from "./scenes/Intro";
import { KpiCards } from "./scenes/KpiCards";
import { Outlook } from "./scenes/Outlook";
import { Outro } from "./scenes/Outro";
import { Segments } from "./scenes/Segments";
import { TrendChart } from "./scenes/TrendChart";
import { alpha, defaultBrand, ThemeContext, type Theme } from "./theme/brand";
import { fontFor } from "./theme/fonts";
import type { SceneData, SceneType, VideoProps } from "./types";

const SCENES: Record<SceneType, React.FC<{ data: SceneData }>> = {
  intro: Intro,
  kpis: KpiCards,
  trend: TrendChart,
  drivers: Drivers,
  segments: Segments,
  outlook: Outlook,
  outro: Outro,
};

const FADE = 10;

/** Fades a scene in and out at its edges (the first scene starts fully visible). */
const Fade: React.FC<{ duration: number; fadeIn: boolean; children: React.ReactNode }> = ({ duration, fadeIn, children }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, FADE, duration - FADE, duration], [fadeIn ? 0 : 1, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

const DemoBadge: React.FC<{ label: string; color: string; start?: boolean }> = ({ label, color, start }) => (
  <div
    style={{
      position: "absolute",
      bottom: 172, // just above the caption band, clear of titles and logo
      [start ? "insetInlineStart" : "insetInlineEnd"]: 24,
      padding: "8px 18px",
      borderRadius: 30,
      background: color,
      color: "white",
      fontSize: 22,
      fontWeight: 600,
    }}
  >
    {label}
  </div>
);

export const QuarterlyVideo: React.FC<VideoProps> = (props) => {
  const { fps, durationInFrames } = useVideoConfig();
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

  // A scene's visuals run from the start of its narration clip to the start of the next one.
  const spans = props.scenes.map((s, i) => {
    const from = i === 0 ? 0 : Math.round(s.audioStart * fps);
    const next = props.scenes[i + 1];
    const to = next ? Math.round(next.audioStart * fps) : durationInFrames;
    return { scene: s, from, duration: Math.max(1, to - from) };
  });

  const audioSrc = props.audio.startsWith("http") ? props.audio : staticFile(props.audio);

  return (
    <ThemeContext.Provider value={theme}>
      <AbsoluteFill
        lang={props.language}
        dir={props.direction}
        style={{ background: brand.colors.background, fontFamily: theme.font, color: brand.colors.ink }}
      >
        <Html5Audio src={audioSrc} />
        {spans.map(({ scene, from, duration }, i) => {
          const Comp = SCENES[scene.type] ?? KpiCards;
          return (
            <Sequence key={scene.id} from={from} durationInFrames={duration} name={`${scene.id} ${scene.type}`}>
              <Fade duration={duration} fadeIn={i > 0}>
                <Comp data={scene.type === "outro" ? { ...scene.data, musicCredit: props.musicCredit } : scene.data} />
              </Fade>
            </Sequence>
          );
        })}
        {props.presenter && <Presenter words={props.words} look={props.presenter} />}
        {props.captions && <Captions words={props.words} />}
        {props.demo && (
          <DemoBadge
            label={props.language === "ar" ? "بيانات تجريبية" : "Demo data"}
            color={alpha(brand.colors.secondary, 0.92)}
            start={Boolean(props.presenter)}
          />
        )}
      </AbsoluteFill>
    </ThemeContext.Provider>
  );
};
