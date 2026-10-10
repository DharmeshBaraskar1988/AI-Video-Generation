import { CalculateMetadataFunction, Composition } from "remotion";
import { QuarterlyVideo } from "./QuarterlyVideo";
import { SOCIAL_SECONDS, SocialCut } from "./SocialCut";
import type { VideoProps } from "./types";
import sampleEn from "../sample.props.json";
import sampleAr from "../sample_ar.props.json";

export const FPS = 30;

// durationInFrames = ceil(durationSeconds * 30), from the props passed with --props
const calculateMetadata: CalculateMetadataFunction<VideoProps> = ({ props }) => ({
  durationInFrames: Math.max(1, Math.ceil(props.durationSeconds * FPS)),
});

export const RemotionRoot: React.FC = () => (
  <>
    {/* Rendered by the back end: npx remotion render src/index.ts QuarterlyVideo out.mp4 --props=props.json */}
    <Composition
      id="QuarterlyVideo"
      component={QuarterlyVideo}
      width={1920}
      height={1080}
      fps={FPS}
      durationInFrames={FPS}
      defaultProps={sampleEn as VideoProps}
      calculateMetadata={calculateMetadata}
    />
    {/* 15-second social cut (intro + KPI scene), rendered from the same props */}
    <Composition
      id="SocialCut"
      component={SocialCut}
      width={1920}
      height={1080}
      fps={FPS}
      durationInFrames={SOCIAL_SECONDS * FPS}
      defaultProps={sampleEn as VideoProps}
    />
    {/* Studio preview of the Arabic (right-to-left) layout */}
    <Composition
      id="QuarterlyVideoArabic"
      component={QuarterlyVideo}
      width={1920}
      height={1080}
      fps={FPS}
      durationInFrames={FPS}
      defaultProps={sampleAr as VideoProps}
      calculateMetadata={calculateMetadata}
    />
  </>
);
