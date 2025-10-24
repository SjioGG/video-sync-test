// video-generator/consumer.js
const amqp = require('amqplib');
const fs = require('fs').promises;
const path = require('path');
const { bundle } = require('@remotion/bundler');
const { renderMedia, selectComposition } = require('@remotion/renderer');

const RABBITMQ_HOST = process.env.RABBITMQ_HOST || 'localhost';
const RABBITMQ_PORT = process.env.RABBITMQ_PORT || 5672;
const RABBITMQ_USER = process.env.RABBITMQ_USER || 'user';
const RABBITMQ_PASSWORD = process.env.RABBITMQ_PASSWORD || 'password';
const OUTPUT_DIR = '/app/shared/videos';

// Ensure output directory exists
fs.mkdir(OUTPUT_DIR, { recursive: true }).catch(console.error);

function parseLRC(lrcContent) {
  const lines = lrcContent.split('\n');
  const lyrics = [];
  
  for (const line of lines) {
    const match = line.match(/\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)/);
    if (match) {
      const minutes = parseInt(match[1]);
      const seconds = parseInt(match[2]);
      const milliseconds = parseInt(match[3].padEnd(3, '0'));
      const text = match[4].trim();
      
      const timeInSeconds = minutes * 60 + seconds + milliseconds / 1000;
      
      if (text) {
        lyrics.push({
          time: timeInSeconds,
          text: text
        });
      }
    }
  }
  
  return lyrics;
}

async function generateRemotionProject(jobId, title, artist, audioPath, lyricsData) {
  const projectDir = path.join('/app', 'projects', jobId);
  await fs.mkdir(projectDir, { recursive: true });
  
  // Create public directory for static assets
  const publicDir = path.join(projectDir, 'public');
  await fs.mkdir(publicDir, { recursive: true });
  
  // Copy audio file to project's public directory
  const audioFilename = path.basename(audioPath);
  const projectAudioPath = path.join(publicDir, audioFilename);
  await fs.copyFile(audioPath, projectAudioPath);
  console.log(`Copied audio file to ${projectAudioPath}`);
  
  // Create package.json for the project
  const packageJson = {
    "name": `lyric-video-${jobId}`,
    "version": "1.0.0",
    "type": "module",
    "dependencies": {
      "react": "^18.2.0",
      "remotion": "^4.0.0"
    }
  };
  
  await fs.writeFile(
    path.join(projectDir, 'package.json'),
    JSON.stringify(packageJson, null, 2)
  );
  
  // Calculate duration based on last lyric
  const lastLyric = lyricsData[lyricsData.length - 1];
  const durationInSeconds = lastLyric ? Math.ceil(lastLyric.time) + 5 : 180;
  const durationInFrames = durationInSeconds * 30;
  
  // Create Root component
  const rootCode = `
import React from 'react';
import { Composition } from 'remotion';
import { LyricVideo } from './Composition.jsx';

export const RemotionRoot = () => {
  return (
    <>
      <Composition
        id="LyricVideo"
        component={LyricVideo}
        durationInFrames={${durationInFrames}}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
`;
  
  await fs.writeFile(path.join(projectDir, 'Root.jsx'), rootCode);
  
  // Create Composition with karaoke-style word highlighting
  const compositionCode = `
import React from 'react';
import { AbsoluteFill, Audio, useCurrentFrame, useVideoConfig, staticFile } from 'remotion';

const lyrics = ${JSON.stringify(lyricsData)};

// Syllable counting for word timing estimation
function countSyllables(word) {
  word = word.toLowerCase().replace(/[^a-z]/g, '');
  if (word.length <= 3) return 1;
  
  word = word.replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, '');
  word = word.replace(/^y/, '');
  
  const syllables = word.match(/[aeiouy]{1,2}/g);
  return syllables ? Math.max(syllables.length, 1) : 1;
}

// Estimate word timings based on syllable distribution
function estimateWordTimings(text, startTime, endTime) {
  const words = text.split(' ').filter(w => w.length > 0);
  if (words.length === 0) return [];
  
  const syllableCounts = words.map(word => countSyllables(word));
  const totalSyllables = syllableCounts.reduce((a, b) => a + b, 0);
  const duration = endTime - startTime;
  
  let currentTime = startTime;
  const wordTimings = [];
  
  for (let i = 0; i < words.length; i++) {
    const syllableRatio = syllableCounts[i] / totalSyllables;
    const wordDuration = syllableRatio * duration;
    
    wordTimings.push({
      word: words[i],
      start: currentTime,
      end: currentTime + wordDuration,
      progress: 0
    });
    
    currentTime += wordDuration;
  }
  
  return wordTimings;
}

export const LyricVideo = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const time = frame / fps;
  
  // Find current lyric index
  let currentIndex = -1;
  for (let i = 0; i < lyrics.length; i++) {
    if (time >= lyrics[i].time) {
      currentIndex = i;
    } else {
      break;
    }
  }
  
  const currentLine = currentIndex >= 0 ? lyrics[currentIndex] : null;
  const nextLine = currentIndex < lyrics.length - 1 ? lyrics[currentIndex + 1] : null;
  
  // Calculate word timings for current line
  let wordTimings = [];
  if (currentLine && nextLine) {
    wordTimings = estimateWordTimings(
      currentLine.text,
      currentLine.time,
      nextLine.time
    );
  } else if (currentLine) {
    // Last line - give it 3 seconds
    wordTimings = estimateWordTimings(
      currentLine.text,
      currentLine.time,
      currentLine.time + 3
    );
  }
  
  // Calculate progress for each word
  const wordsWithProgress = wordTimings.map(wt => {
    let progress = 0;
    if (time >= wt.end) {
      progress = 1;
    } else if (time >= wt.start) {
      progress = (time - wt.start) / (wt.end - wt.start);
    }
    return { ...wt, progress };
  });
  
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Audio src={staticFile('${audioFilename}')} volume={1.0} />
      <AbsoluteFill style={{
        justifyContent: 'center',
        alignItems: 'center',
        padding: '80px',
      }}>
        {currentLine && (
          <div style={{
            fontSize: '72px',
            textAlign: 'center',
            fontWeight: 'bold',
            fontFamily: 'Arial, sans-serif',
            maxWidth: '90%',
            lineHeight: '1.4',
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            gap: '20px',
          }}>
            {wordsWithProgress.map((wt, i) => (
              <span key={i} style={{
                position: 'relative',
                display: 'inline-block',
              }}>
                {/* Background text (unsung - gray) */}
                <span style={{
                  color: '#444',
                  textShadow: '2px 2px 4px rgba(0,0,0,0.8)',
                }}>
                  {wt.word}
                </span>
                {/* Foreground text (sung - bright with gradient, clips with progress) */}
                <span style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  color: '#fff',
                  textShadow: '3px 3px 6px rgba(0,0,0,0.9), 0 0 20px rgba(79,195,247,0.6)',
                  background: 'linear-gradient(90deg, #fff 0%, #4fc3f7 50%, #fff 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                  clipPath: \`inset(0 \${100 - (wt.progress * 100)}% 0 0)\`,
                }}>
                  {wt.word}
                </span>
              </span>
            ))}
          </div>
        )}
        
        {/* Song info at bottom */}
        <div style={{
          position: 'absolute',
          bottom: '100px',
          left: '0',
          right: '0',
          textAlign: 'center',
        }}>
          <div style={{
            fontSize: '32px',
            color: '#aaa',
            fontFamily: 'Arial, sans-serif',
            marginBottom: '10px',
          }}>
            ${title.replace(/'/g, "\\'")}
          </div>
          <div style={{
            fontSize: '24px',
            color: '#888',
            fontFamily: 'Arial, sans-serif',
          }}>
            ${artist.replace(/'/g, "\\'")}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
`;
  
  await fs.writeFile(path.join(projectDir, 'Composition.jsx'), compositionCode);
  
  // Create entry point
  const entryCode = `
import { registerRoot } from 'remotion';
import { RemotionRoot } from './Root.jsx';

registerRoot(RemotionRoot);
`;
  
  await fs.writeFile(path.join(projectDir, 'index.jsx'), entryCode);
  
  return { projectDir, audioFilename };
}

async function renderVideo(projectDir, outputPath, audioFilename) {
  console.log('Bundling Remotion project...');
  
  const bundleLocation = await bundle({
    entryPoint: path.join(projectDir, 'index.jsx'),
    publicDir: path.join(projectDir, 'public'),
    webpackOverride: (config) => config,
  });
  
  console.log('Selecting composition...');
  
  const composition = await selectComposition({
    serveUrl: bundleLocation,
    id: 'LyricVideo',
  });
  
  console.log(`Rendering video: ${composition.width}x${composition.height}, ${composition.durationInFrames} frames...`);
  
  await renderMedia({
    composition,
    serveUrl: bundleLocation,
    codec: 'h264',
    outputLocation: outputPath,
    // IMPORTANT: Force audio mixing
    audioCodec: 'aac',
    audioBitrate: '320k',
    muted: false,
    enforceAudioTrack: true,
    chromiumOptions: {
      headless: true,
    },
    onProgress: ({ progress, renderedFrames, encodedFrames }) => {
      if (renderedFrames % 30 === 0) {
        console.log(`Progress: ${(progress * 100).toFixed(1)}% (${renderedFrames}/${composition.durationInFrames} frames)`);
      }
    },
  });
  
  console.log('Video rendered successfully!');
  return true;
}

async function processVideoRequest(message) {
  const { job_id, title, artist, audio_path, lyrics_path, has_sync } = message;
  
  console.log(`Processing video generation for job ${job_id}`);
  
  try {
    // Read lyrics file
    const lyricsContent = await fs.readFile(lyrics_path, 'utf-8');
    const lyricsData = parseLRC(lyricsContent);
    
    if (lyricsData.length === 0) {
      console.error('No valid lyrics data found');
      return;
    }
    
    console.log(`Found ${lyricsData.length} lyric lines`);
    
    // Generate Remotion project
    const { projectDir, audioFilename } = await generateRemotionProject(
      job_id,
      title,
      artist,
      audio_path,
      lyricsData
    );
    
    // Render video
    const outputPath = path.join(OUTPUT_DIR, `${job_id}.mp4`);
    await renderVideo(projectDir, outputPath, audioFilename);
    
    console.log(`✅ Successfully generated video: ${outputPath}`);
    
  } catch (error) {
    console.error('❌ Error processing video request:', error);
  }
}

async function connectRabbitMQ() {
  const maxRetries = 10;
  const retryDelay = 5000;
  
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const connection = await amqp.connect({
        protocol: 'amqp',
        hostname: RABBITMQ_HOST,
        port: RABBITMQ_PORT,
        username: RABBITMQ_USER,
        password: RABBITMQ_PASSWORD,
      });
      
      const channel = await connection.createChannel();
      await channel.assertQueue('video_requests', { durable: true });
      
      console.log('Connected to RabbitMQ');
      return { connection, channel };
    } catch (error) {
      console.warn(`Connection attempt ${attempt + 1} failed:`, error.message);
      if (attempt < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, retryDelay));
      } else {
        throw error;
      }
    }
  }
}

async function main() {
  const { connection, channel } = await connectRabbitMQ();
  
  channel.prefetch(1);
  
  console.log('🎬 Video Generator Service started. Waiting for messages...');
  
  channel.consume('video_requests', async (msg) => {
    if (msg !== null) {
      try {
        const message = JSON.parse(msg.content.toString());
        await processVideoRequest(message);
        channel.ack(msg);
      } catch (error) {
        console.error('Error processing message:', error);
        channel.nack(msg, false, false);
      }
    }
  });
}

main().catch(console.error);