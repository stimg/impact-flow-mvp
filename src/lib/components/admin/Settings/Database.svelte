<script lang="ts">
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { downloadDatabase } from '$lib/apis/utils';
	import { onMount, getContext } from 'svelte';
	import { config } from '$lib/stores';
	import { toast } from 'svelte-sonner';
	import { getAllUserChats } from '$lib/apis/chats';
	import { exportConfig, importConfig } from '$lib/apis/configs';
	import Textarea from "$lib/components/common/Textarea.svelte";

	type Product = {
		id: string;
		name: string;
		short_description: string;
		product_details: string;
		target_audience?: string;
		tags?: string;
		similar_products?: string;
		recommended_products?: string;
		supporting_products?: string;
		combinable_with?: string;
		categories?: string;
		application_area?: string;
		ingredients?: string;
		formulation_origin?: string;
		history?: string;
		user_experience?: string;
		intake_recommendation?: string;
		reference_link?: string;
		document_url?: string;
		source?: string;
	}

	const i18n = getContext('i18n');

	export let saveHandler: Function;
	export let generateEmbeddingsHandler: (token: string, id: string, metadata: object) => void;
	export let getProductByNameHandler: (token: string, name: string) => Promise<Product> | undefined;
	export let id = '';
	export let name = '';
	export let tags = '';
	export let similar_products = '';
	export let recommended_products = '';
	export let supporting_products = '';
	export let combinable_with = '';
	export let short_description = '';
	export let product_details = '';
	export let target_audience = '';
	export let categories = '';
	export let intake_recommendation = '';
	export let application_area = '';
	export let ingredients = '';
	export let formulation_origin = '';
	export let history = '';
	export let user_experience = '';
	export let source = 'https://www.ethno-health.com';
	export let reference_link = '';

	const getMetadata = (): Product => ({
		id: `${$i18n.t('Product ID')}: ${id}`,
		name: `${$i18n.t('Product Name')}: ${name}`,
		categories: `${$i18n.t('Categories')}: ${categories}`,
		tags: `${$i18n.t('Tags')}: ${tags}`,
		similar_products: `${$i18n.t('Similar products')}: ${similar_products}`,
		recommended_products: `${$i18n.t('Recommended products')}: ${recommended_products}`,
		supporting_products: `${$i18n.t('Supporting products')}: ${supporting_products}`,
		combinable_with: `${$i18n.t('Combinable with products')}: ${combinable_with}`,
		short_description: `${$i18n.t('Short description')}: ${short_description}`,
		product_details: `${$i18n.t('Product details')}: ${product_details}`,
		target_audience: `${$i18n.t('Target audience')}: ${target_audience}`,
		intake_recommendation: `${$i18n.t('Intake recommendation')}: ${intake_recommendation}`,
		application_area: `${$i18n.t('Application area')}: ${application_area}`,
		ingredients: `${$i18n.t('Ingredients')}: ${ingredients}`,
		formulation_origin: `${$i18n.t('Formulation origin')}: ${formulation_origin}`,
		history: `${$i18n.t('History')}: ${history}`,
		user_experience: `${$i18n.t('User experience')}: ${user_experience}`,
		source:	`${$i18n.t('Manufacturers homepage')}: ${source}`,
		reference_link: `${$i18n.t('Product webpage')}: ${reference_link}`,
	})

	const setProductData = (product: Product) => {
		id = product.id;
		name = product.name;
		categories = product.categories || '';
		tags = product.tags || '';
		similar_products = product.similar_products || '';
		recommended_products = product.recommended_products || '';
		supporting_products = product.supporting_products || '';
		combinable_with = product.combinable_with || '';
		short_description = product.short_description || '';
		product_details = product.product_details || '';
		target_audience = product.target_audience || '';
		intake_recommendation = product.intake_recommendation || '';
		application_area = product.application_area || '';
		ingredients = product.ingredients || '';
		formulation_origin = product.formulation_origin || '';
		history = product.history || '';
		user_experience = product.user_experience || '';
		reference_link = product.reference_link || '';
	}

	const resetProductData = () => {
		id = '';
		name = '';
		categories = '';
		tags = '';
		similar_products = '';
		recommended_products = '';
		supporting_products = '';
		combinable_with = '';
		short_description = '';
		product_details = '';
		target_audience = '';
		intake_recommendation = '';
		application_area = '';
		ingredients = '';
		formulation_origin = '';
		history = '';
		user_experience = '';
		reference_link = '';
	}

	const exportAllUserChats = async () => {
		let blob = new Blob([JSON.stringify(await getAllUserChats(localStorage.token))], {
			type: 'application/json'
		});
		saveAs(blob, `all-chats-export-${Date.now()}.json`);
	};

	onMount(async () => {
		// permissions = await getUserPermissions(localStorage.token);
	});

	const onSubmit = async (evt) => {
		generateEmbeddingsHandler(localStorage.token, id, getMetadata());
		evt.target.reset()
	}
	const onSearchProduct = async () => {
		const product = await getProductByNameHandler(localStorage.token, search_name);
		if (product) {
            setProductData(product);
        }
	}

	const onResetForm = (evt) => {
		evt.target.querySelectorAll('textarea').forEach((el: HTMLInputElement) => {
			el.style.height = '';
		})
		resetProductData();
	}

	let search_name = ''
</script>

<form
	class="flex flex-col justify-between space-y-3 text-sm"
	on:submit|preventDefault={async () => {
		saveHandler();
	}}
>
	<div class=" space-y-3 overflow-y-scroll scrollbar-hidden">
		<div>
			<div class=" mb-2 text-lg font-medium">{$i18n.t('Database')}</div>

			<input
				id="config-json-input"
				hidden
				type="file"
				accept=".json"
				on:change={(e) => {
					const file = e.target.files[0];
					const reader = new FileReader();

					reader.onload = async (e) => {
						const res = await importConfig(localStorage.token, JSON.parse(e.target.result)).catch(
							(error) => {
								toast.error(`${error}`);
							}
						);

						if (res) {
							toast.success('Config imported successfully');
						}
						e.target.value = null;
					};

					reader.readAsText(file);
				}}
			/>

			<button
				type="button"
				class=" flex rounded-md py-2 px-3 w-full hover:bg-gray-200 dark:hover:bg-gray-800 transition"
				on:click={async () => {
					document.getElementById('config-json-input').click();
				}}
			>
				<div class=" self-center mr-3">
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 16 16"
						fill="currentColor"
						class="w-4 h-4"
					>
						<path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3Z" />
						<path
							fill-rule="evenodd"
							d="M13 6H3v6a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V6ZM8.75 7.75a.75.75 0 0 0-1.5 0v2.69L6.03 9.22a.75.75 0 0 0-1.06 1.06l2.5 2.5a.75.75 0 0 0 1.06 0l2.5-2.5a.75.75 0 1 0-1.06-1.06l-1.22 1.22V7.75Z"
							clip-rule="evenodd"
						/>
					</svg>
				</div>
				<div class=" self-center text-sm font-medium">
					{$i18n.t('Import Config from JSON File')}
				</div>
			</button>

			<button
				type="button"
				class=" flex rounded-md py-2 px-3 w-full hover:bg-gray-200 dark:hover:bg-gray-800 transition"
				on:click={async () => {
					const config = await exportConfig(localStorage.token);
					const blob = new Blob([JSON.stringify(config)], {
						type: 'application/json'
					});
					saveAs(blob, `config-${Date.now()}.json`);
				}}
			>
				<div class=" self-center mr-3">
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 16 16"
						fill="currentColor"
						class="w-4 h-4"
					>
						<path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3Z" />
						<path
							fill-rule="evenodd"
							d="M13 6H3v6a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V6ZM8.75 7.75a.75.75 0 0 0-1.5 0v2.69L6.03 9.22a.75.75 0 0 0-1.06 1.06l2.5 2.5a.75.75 0 0 0 1.06 0l2.5-2.5a.75.75 0 1 0-1.06-1.06l-1.22 1.22V7.75Z"
							clip-rule="evenodd"
						/>
					</svg>
				</div>
				<div class=" self-center text-sm font-medium">
					{$i18n.t('Export Config to JSON File')}
				</div>
			</button>

			<hr class="border-gray-100 dark:border-gray-850 my-1" />

			{#if $config?.features.enable_admin_export ?? true}
				<div class="  flex w-full justify-between">
					<!-- <div class=" self-center text-xs font-medium">{$i18n.t('Allow Chat Deletion')}</div> -->

					<button
						class=" flex rounded-md py-1.5 px-3 w-full hover:bg-gray-200 dark:hover:bg-gray-800 transition"
						type="button"
						on:click={() => {
							// exportAllUserChats();

							downloadDatabase(localStorage.token).catch((error) => {
								toast.error(`${error}`);
							});
						}}
					>
						<div class=" self-center mr-3">
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="w-4 h-4"
							>
								<path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3Z" />
								<path
									fill-rule="evenodd"
									d="M13 6H3v6a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V6ZM8.75 7.75a.75.75 0 0 0-1.5 0v2.69L6.03 9.22a.75.75 0 0 0-1.06 1.06l2.5 2.5a.75.75 0 0 0 1.06 0l2.5-2.5a.75.75 0 1 0-1.06-1.06l-1.22 1.22V7.75Z"
									clip-rule="evenodd"
								/>
							</svg>
						</div>
						<div class=" self-center text-sm font-medium">{$i18n.t('Download Database')}</div>
					</button>
				</div>

				<button
					class=" flex rounded-md py-2 px-3 w-full hover:bg-gray-200 dark:hover:bg-gray-800 transition"
					on:click={() => {
						exportAllUserChats();
					}}
				>
					<div class=" self-center mr-3">
						<svg
							xmlns="http://www.w3.org/2000/svg"
							viewBox="0 0 16 16"
							fill="currentColor"
							class="w-4 h-4"
						>
							<path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3Z" />
							<path
								fill-rule="evenodd"
								d="M13 6H3v6a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V6ZM8.75 7.75a.75.75 0 0 0-1.5 0v2.69L6.03 9.22a.75.75 0 0 0-1.06 1.06l2.5 2.5a.75.75 0 0 0 1.06 0l2.5-2.5a.75.75 0 1 0-1.06-1.06l-1.22 1.22V7.75Z"
								clip-rule="evenodd"
							/>
						</svg>
					</div>
					<div class=" self-center text-sm font-medium">
						{$i18n.t('Export All Chats (All Users)')}
					</div>
				</button>
			{/if}
		</div>
	</div>

	<!-- <div class="flex justify-end pt-3 text-sm font-medium">
		<button
			class=" px-4 py-2 bg-emerald-700 hover:bg-emerald-800 text-gray-100 transition rounded-lg"
			type="submit"
		>
			{$i18n.t('Save')}
		</button>

	</div> -->
</form>

<div>
	<div class="text-lg font-semibold mb-2 mt-10">
		{$i18n.t('Produkt anlegen oder bearbeiten')}
	</div>
	<div>
		<form  class="flex justify-between space-y-3 text-sm"
		   on:submit|preventDefault={onSearchProduct}>
			<span class="flex-1">
				<input class="w-full" type="text" bind:value="{search_name}" placeholder="🔎 {$i18n.t('Search product by name')}">
				<div class="text-xs text-gray-500">{$i18n.t('To update a product, first find it by name to populate its fields.')}</div>
			</span>
			<span class="flex-none">
				<input type="submit" class="button w-fit mb-3 ml-5" value="{$i18n.t('Search')}" disabled={name.length !== 0}>
			</span>
		</form>
	</div>
	<form class="flex flex-col justify-between space-y-3 text-sm" on:submit|preventDefault={onSubmit} on:reset|preventDefault={onResetForm}>

		<input type="hidden" bind:value="{id}" placeholder="{$i18n.t('Wird ein neues Produkt angelegt, wenn leer')}">

		<label class="mb-0" for="name">{$i18n.t('Product name')}</label>
		<input type="text" bind:value="{name}">

		<label class="mb-0" for="Categories">{$i18n.t('Categories')}</label>
		<input type="text" bind:value="{categories}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Tibetische Rezeptur Lung')}">

		<label class="mb-0" for="Tags">{$i18n.t('Tags')}</label>
		<input type="text" bind:value="{tags}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Shake, Shape Classic, Abnehmen, Wohlfühlen , Konzept')}">

		<label class="mb-0" for="Categories">{$i18n.t('Recommended products')}</label>
		<input type="text" bind:value="{recommended_products}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Omega Go!, Omega 3 Orange')}">

		<label class="mb-0" for="Tags">{$i18n.t('Similar products')}</label>
		<input type="text" bind:value="{similar_products}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Algenkraft, Gehirnkraft, Darmkraft')}">

		<label class="mb-0" for="Tags">{$i18n.t('Supporting products')}</label>
		<input type="text" bind:value="{supporting_products}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Chili Shoko Shake, Burner, daily 365')}">

		<label class="mb-0" for="Categories">{$i18n.t('Combinable with products')}</label>
		<input type="text" bind:value="{combinable_with}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Lung, Omega Go!, Omega 3 Orange')}">

		<label class="mb-0" for="short_description">{$i18n.t('Short description')}</label>
		<Textarea bind:value="{short_description}" />

		<label class="mb-0" for="product_details">{$i18n.t('Product details')}</label>
		<Textarea bind:value="{product_details}" />

		<label class="mb-0" for="target_audience">{$i18n.t('Target audience')}</label>
		<Textarea bind:value="{target_audience}" />

		<label class="mb-0" for="application_area">{$i18n.t('Application area')}</label>
		<Textarea bind:value="{application_area}" />

		<label class="mb-0" for="formulation_origin">{$i18n.t('Formulation origin')}</label>
		<Textarea bind:value="{formulation_origin}" />

		<label class="mb-0" for="intake_recommendation">{$i18n.t('Intake recommendation')}</label>
		<Textarea bind:value="{intake_recommendation}" />

		<label class="mb-0" for="ingredients">{$i18n.t('Ingredients')}</label>
		<Textarea bind:value="{ingredients}" />

		<label class="mb-0" for="history">{$i18n.t('History')}</label>
		<Textarea bind:value="{history}" />

		<label class="mb-0" for="user_experience">{$i18n.t('User experience')}</label>
		<Textarea bind:value="{user_experience}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Monika S., 57 Jahre. \"Es ist erstaunlich, wie einfach es sein kann, für die eigene Gesundheit etwas zu tun... \"')}" />

		<label class="mb-0" for="reference_link">{$i18n.t('Product webpage')}</label>
		<input type="text" bind:value="{reference_link}" placeholder="ℹ️ {$i18n.t('Direkter Link zum Produkt im Shop oder Webseite')}">

 		<div class="text-center mb-10">
			<input type="reset" value="{$i18n.t('Zurücksetzen')}" class="button w-fit mt-5 mr-3">
			<input type="submit" value="{$i18n.t('Save')}" class="button w-fit mt-5" disabled={name.length === 0}>
		</div>
	</form>
</div>
