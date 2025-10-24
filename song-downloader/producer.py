# producer.py
import pika
import json
import uuid

def send_job(youtube_url):
    """Send a job to the song downloader service"""
    credentials = pika.PlainCredentials('user', 'password')
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host='localhost', port=5672, credentials=credentials)
    )
    channel = connection.channel()
    
    channel.queue_declare(queue='song_requests', durable=True)
    
    job_id = str(uuid.uuid4())
    message = {
        'job_id': job_id,
        'youtube_url': youtube_url
    }
    
    channel.basic_publish(
        exchange='',
        routing_key='song_requests',
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    
    print(f"Sent job {job_id} for {youtube_url}")
    connection.close()
    return job_id

if __name__ == '__main__':
    youtube_url = input("Enter YouTube URL: ")
    job_id = send_job(youtube_url)
    print(f"Job ID: {job_id}")
