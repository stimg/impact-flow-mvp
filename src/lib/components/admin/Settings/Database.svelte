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
	import Switch from "$lib/components/common/Switch.svelte";

	type Product = {
		name: string;
		short_description: string;
		target_audience?: string;
		tags?: string;
		categories?: string;
		product_details: string;
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
	export let generateEmbeddingsHandler: (token: string, id: string, content: string, metadata: object, overwrite: boolean) => void;
	export let overwrite = true;
	export let id = '';
	export let name = '';
	export let short_description = '';
	export let product_details = '';
	export let target_audience = '';
	export let tags = '';
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
		name: `${$i18n.t('Product Name')}: ${name}`,
		short_description: `${$i18n.t('Short description')}: ${short_description}`,
		product_details: `${$i18n.t('Product details')}: ${product_details}`,
		target_audience: `${$i18n.t('Target audience')}: ${target_audience}`,
		tags: `${$i18n.t('Tags')}: ${tags}`,
		categories: `${$i18n.t('Categories')}: ${categories}`,
		intake_recommendation: `${$i18n.t('Intake recommendation')}: ${intake_recommendation}`,
		application_area: `${$i18n.t('Application area')}: ${application_area}`,
		ingredients: `${$i18n.t('Ingredients')}: ${ingredients}`,
		formulation_origin: `${$i18n.t('Formulation origin')}: ${formulation_origin}`,
		history: `${$i18n.t('History')}: ${history}`,
		user_experience: `${$i18n.t('User experience')}: ${user_experience}`,
		source:	`${$i18n.t('Manufacturers homepage')}: ${source}`,
		reference_link: `${$i18n.t('Product webpage')}: ${reference_link}`,
	})

	const exportAllUserChats = async () => {
		let blob = new Blob([JSON.stringify(await getAllUserChats(localStorage.token))], {
			type: 'application/json'
		});
		saveAs(blob, `all-chats-export-${Date.now()}.json`);
	};

	onMount(async () => {
		// permissions = await getUserPermissions(localStorage.token);
	});
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
		{$i18n.t('Generate product embeddings')}
	</div>
	<form class="flex flex-col justify-between space-y-3 text-sm"
		  on:submit|preventDefault={async () => generateEmbeddingsHandler(localStorage.token, id, getMetadata(), overwrite)}>

		<label class="mb-0" for="db_product_id">{$i18n.t('Product ID')}</label>
		<input type="text" bind:value="{id}" placeholder="{$i18n.t('Wird ein neues Produkt angelegt, wenn leer')}">

		<label class="mb-0" for="db_product_name">{$i18n.t('Product name')}</label>
		<input type="text" bind:value="{name}">

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

		<label class="mb-0" for="Tags">{$i18n.t('Tags')}</label>
		<input type="text" bind:value="{tags}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Shake, Shape Classic, Abnehmen, Wohlfühlen , Konzept')}">

		<label class="mb-0" for="Categories">{$i18n.t('Categories')}</label>
		<input type="text" bind:value="{categories}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Tibetische Rezeptur Lung')}">

		<label class="mb-0" for="reference_link">{$i18n.t('Product webpage')}</label>
		<input type="text" bind:value="{reference_link}" placeholder="ℹ️ {$i18n.t('Direkter Link zum Produkt im Shop oder Webseite')}">

		<div class="mb-2.5 mt-3 flex justify-center">
			<div class="text-sm font-medium mr-5">
				{$i18n.t('Overwrite existing')}
			</div>
			<Switch bind:state={overwrite} />
		</div>
 		<div class="text-center">
			<input type="reset" value="{$i18n.t('Zurücksetzen')}" class="button w-fit mt-5 mr-3">
			<input type="submit" value="{$i18n.t('Generate')}" class="button w-fit mt-5">
		</div>
	</form>
</div>
