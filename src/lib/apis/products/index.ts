import { PRODUCTS_API_BASE_URL } from '$lib/constants';

export const getProductByName = async (
	token: string,
	name: string,
) => {
	let error = null;

	const res = await fetch(`${PRODUCTS_API_BASE_URL}/?product_name=${encodeURIComponent(name)}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const processProduct = async (
	token: string,
	id: string,
	content: string = '' ,
	metadata = {},
) => {
	let error = null;

	const res = await fetch(`${PRODUCTS_API_BASE_URL}/process`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},

		body: JSON.stringify({
			id,
			content,
			metadata,
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

