from flask import Flask, render_template, request, jsonify
import asyncio
import aiohttp
import os
from typing import List, Dict
import json
from datetime import datetime
import re

app = Flask(__name__)

TOKENS_FILE = 'tokens.json'

class ShareManager:
    def __init__(self):
        self.error_count = 0
        self.success_count = 0
        self.total_shares = 0
        self.target_shares = 0
        
    async def share(self, session: aiohttp.ClientSession, token: str, post_id: str, share_count: int):
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'accept-encoding': 'gzip, deflate',
            'host': 'graph.facebook.com'
        }
        
        retries = 3
        while self.total_shares < self.target_shares and retries > 0:
            try:
                async with session.post(
                    'https://graph.facebook.com/me/feed',
                    params={
                        'link': f'https://facebook.com/{post_id}',
                        'published': '0',
                        'access_token': token
                    },
                    headers=headers,
                    timeout=30
                ) as response:
                    data = await response.json()
                    if 'id' in data:
                        self.total_shares += 1
                        self.success_count += 1
                    else:
                        self.error_count += 1
                        retries -= 1
            except Exception:
                self.error_count += 1
                retries -= 1
                await asyncio.sleep(1)

def load_tokens() -> List[str]:
    try:
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, 'r') as f:
                data = json.load(f)
                return data.get('tokens', [])
        return []
    except Exception:
        return []

def save_tokens(tokens: List[str]) -> bool:
    try:
        with open(TOKENS_FILE, 'w') as f:
            json.dump({'tokens': list(set(tokens))}, f)  # Remove duplicates
        return True
    except Exception:
        return False

@app.route('/')
def index():
    tokens = load_tokens()
    return render_template('index.html', token_count=len(tokens), tokens=tokens)

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    tokens = load_tokens()
    return jsonify({'tokens': tokens})

@app.route('/api/tokens', methods=['POST'])
def add_tokens():
    data = request.json
    if 'tokens' in data:  # Bulk import
        new_tokens = data['tokens']
        if isinstance(new_tokens, str):  # If it's a string, split by newlines
            new_tokens = [t.strip() for t in new_tokens.split('\n') if t.strip()]
    else:  # Single token
        new_tokens = [data.get('token', '').strip()]
    
    if not new_tokens:
        return jsonify({'status': 'error', 'message': 'No valid tokens provided'}), 400

    existing_tokens = load_tokens()
    updated_tokens = list(set(existing_tokens + new_tokens))  # Remove duplicates
    
    if save_tokens(updated_tokens):
        return jsonify({
            'status': 'success',
            'message': f'Added {len(updated_tokens) - len(existing_tokens)} new tokens',
            'total_tokens': len(updated_tokens)
        })
    return jsonify({'status': 'error', 'message': 'Failed to save tokens'}), 500

@app.route('/api/tokens/<token>', methods=['DELETE'])
def delete_token(token):
    tokens = load_tokens()
    if token in tokens:
        tokens.remove(token)
        if save_tokens(tokens):
            return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Token not found'}), 404

@app.route('/api/tokens/clear', methods=['POST'])
def clear_tokens():
    if save_tokens([]):
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Failed to clear tokens'}), 500

@app.route('/api/share', methods=['POST'])
def share():
    data = request.json
    post_id = data.get('post_id')
    share_count = data.get('share_count')
    
    if not post_id or not post_id.isdigit():
        return jsonify({'status': 'error', 'message': 'Invalid Post ID format'})
    
    try:
        share_count = int(share_count)
        if not (0 < share_count <= 1000):
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid share count'})
    
    tokens = load_tokens()
    if not tokens:
        return jsonify({'status': 'error', 'message': 'No tokens available'})
    
    share_manager = ShareManager()
    share_manager.target_shares = share_count * len(tokens)
    
    async def process_shares():
        async with aiohttp.ClientSession() as session:
            tasks = [
                share_manager.share(session, token, post_id, share_count)
                for token in tokens
            ]
            await asyncio.gather(*tasks)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(process_shares())
    loop.close()
    
    return jsonify({
        'status': 'success',
        'total_shares': share_manager.total_shares,
        'successful': share_manager.success_count,
        'failed': share_manager.error_count
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
