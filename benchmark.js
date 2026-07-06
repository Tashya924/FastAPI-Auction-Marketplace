import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

// Load the environment variables from the JSON file
const data = new SharedArray('env data', function () {
    return [JSON.parse(open('./benchmark_env.json'))];
});

export const options = {
    scenarios: {
        concurrent_bids: {
            executor: 'ramping-vus',
            startVUs: 10,
            stages: [
                { duration: '10s', target: 50 },
                { duration: '20s', target: 50 },
                { duration: '5s', target: 0 },
            ],
        },
    },
    thresholds: {
        http_req_failed: ['rate<0.01'], // 400 is technically a failure in k6, let's track it separately
    },
};

export default function () {
    const env = data[0];
    const auction_id = env.auction_id;
    const token = env.token;

    const url = `http://127.0.0.1:8000/auctions/${auction_id}/bid`;
    
    // We need a strictly increasing bid amount to ensure 200 OKs. 
    // We'll use a large timestamp + VU ID to prevent collisions and keep it growing.
    const bidAmount = Date.now() + (__VU * 1000) + __ITER;

    const payload = JSON.stringify({
        amount: bidAmount,
    });

    const params = {
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
    };

    const res = http.post(url, payload, params);

    // Both 200 (Bid placed) and 400 (Bid must be greater) mean the DB lock was successfully acquired and processed.
    check(res, {
        'is status 200 or 400': (r) => r.status === 200 || r.status === 400,
        'is status 200': (r) => r.status === 200,
    });
    
    // Small sleep to simulate realistic user pacing
    sleep(0.01);
}
