import grpc
from concurrent import futures
import logging
import os
import soundfile as sf
import torch
from df.enhance import init_df, enhance, save_audio
import audio_enhancement_pb2
import audio_enhancement_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize DeepFilterNet model
logger.info("🎤 Initializing DeepFilterNet...")
df_model, df_state, _ = init_df()
logger.info("✅ DeepFilterNet loaded!")


class AudioEnhancerServicer(audio_enhancement_pb2_grpc.AudioEnhancerServicer):
    def EnhanceAudio(self, request, context):
        """Enhance audio using DeepFilterNet"""
        try:
            input_path = request.input_path
            output_path = request.output_path
            
            logger.info(f"🎤 Enhancing: {input_path} -> {output_path}")
            
            # Check if input file exists
            if not os.path.exists(input_path):
                error_msg = f"Input file not found: {input_path}"
                logger.error(error_msg)
                return audio_enhancement_pb2.EnhanceResponse(
                    success=False,
                    error=error_msg,
                    output_path=""
                )
            
            # Load audio
            noisy, sr = sf.read(input_path, dtype="float32")
            
            # Convert to tensor
            if noisy.ndim == 1:  # mono
                noisy_t = torch.from_numpy(noisy).unsqueeze(0)
            else:
                noisy_t = torch.from_numpy(noisy).T  # [channels, samples]
            
            # Enhance using DeepFilterNet
            enhanced = enhance(df_model, df_state, noisy_t)
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save enhanced audio
            save_audio(output_path, enhanced, sr=sr)
            
            logger.info(f"✅ Enhanced audio saved: {output_path}")
            
            return audio_enhancement_pb2.EnhanceResponse(
                success=True,
                error="",
                output_path=output_path
            )
            
        except Exception as e:
            error_msg = f"Enhancement failed: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            
            return audio_enhancement_pb2.EnhanceResponse(
                success=False,
                error=error_msg,
                output_path=""
            )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    audio_enhancement_pb2_grpc.add_AudioEnhancerServicer_to_server(
        AudioEnhancerServicer(), server
    )
    server.add_insecure_port('[::]:50051')
    server.start()
    
    logger.info("=" * 60)
    logger.info("🎤 Speech Enhancement Service")
    logger.info("   gRPC server listening on port 50051")
    logger.info("=" * 60)
    
    server.wait_for_termination()


if __name__ == '__main__':
    serve()
