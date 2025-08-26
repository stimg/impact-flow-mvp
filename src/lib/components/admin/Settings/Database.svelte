<script lang="ts">
    import fileSaver from 'file-saver';
    import {getContext, onMount} from 'svelte';
    import {config} from '$lib/stores';
    import {toast} from 'svelte-sonner';
    import {getAllUserChats} from '$lib/apis/chats';
    import {exportConfig, importConfig} from '$lib/apis/configs';
    import Textarea from "$lib/components/common/Textarea.svelte";

    const {saveAs} = fileSaver;

    type Product = {
        id: string;
        name: string;
        categories: string;
        tags: string;
        short_description: string;
        ingredients: string;
        intake_recommendation: string;
        reference_link: string;
        product_details?: string;
        target_audience?: string;
        similar_products?: string;
        recommended_products?: string;
        supporting_products?: string;
        combinable_with?: string;
        application_area?: string;
        formulation_origin?: string;
        history?: string;
        hint?: string;
        user_experience?: string;
        document_url?: string;
        source?: string;
    }

    type QNA = {
        id: string;
        scope: string;
        question: string;
        answer: string;
        hint: string;
    }

    type Recommendation = {
        id: string;
        tags: string;
        recommended: string;
        suitable: string;
        info: string;
        hint: string;
    }

    const i18n = getContext('i18n');
    export let disabled = true;
    export let qna_disabled = true;
    export let recommendations_disabled = true;

    export let saveHandler: Function;

    export let processProductHandler: (token: string, id: string, metadata: object) => void;
    export let getProductByNameHandler: (token: string, name: string) => Promise<Product> | undefined;

    export let processQNAHandler: (token: string, id: string, metadata: object) => void;
    export let getQNAByQuestionHandler: (token: string, name: string) => Promise<QNA> | undefined;

    export let processRecommendationHandler: (token: string, id: string, metadata: Record<string, unknown>) => void;
    export let getRecommendationByTagHandler: (token: string, tag: string) => Promise<Recommendation> | undefined;

    export let product_id = '';
    export let product_name = '';
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
    export let prod_hint = '';
    export let user_experience = '';
    export let source = 'https://www.ethno-health.com';
    export let reference_link = '';

    export let qna_id = '';
    export let scope = '';
    export let question = '';
    export let answer = '';
    export let qna_hint = '';

    export let rec_id = '';
    export let rec_tags = '';
    export let recommended = '';
    export let suitable = '';
    export let info = '';
    export let rec_hint = '';

    const exportAllUserChats = async () => {
        let blob = new Blob([JSON.stringify(await getAllUserChats(localStorage.token))], {
            type: 'application/json'
        });
        saveAs(blob, `all-chats-export-${Date.now()}.json`);
    };

    onMount(async () => {
        // permissions = await getUserPermissions(localStorage.token);
    });

    const setProductSubmitDisabled = () =>
        disabled = !product_name
            || !categories
            || !tags
            || !short_description
            || !ingredients
            || !intake_recommendation
            || !reference_link

    const setQNASubmitDisabled = () =>
        qna_disabled = !scope
            || !question
            || !answer

    const setRecommendationSubmitDisabled = () =>
        recommendations_disabled = !recommended
            || !suitable
            || !info
            || !rec_tags

    const getProductMetadata = (): Omit<Product, 'id'> => ({
        name: product_name,
        categories: `${$i18n.t('Categories')}: ${categories}`,
        tags: tags ? `${$i18n.t('Tags')}: ${tags}` : '',
        similar_products: similar_products ? `${$i18n.t('Similar products')}: ${similar_products}` : '',
        recommended_products: recommended_products ? `${$i18n.t('Recommended products')}: ${recommended_products}` : '',
        supporting_products: supporting_products ? `${$i18n.t('Supporting products')}: ${supporting_products}` : '',
        combinable_with: combinable_with ? `${$i18n.t('Combinable with products')}: ${combinable_with}` : '',
        short_description: short_description ? `${$i18n.t('Short description')}: ${short_description}` : '',
        product_details: product_details ? `${$i18n.t('Product details')}: ${product_details}` : '',
        target_audience: target_audience ? `${$i18n.t('Target audience')}: ${target_audience}` : '',
        intake_recommendation: intake_recommendation ? `${$i18n.t('Intake recommendation')}: ${intake_recommendation}` : '',
        application_area: application_area ? `${$i18n.t('Application area')}: ${application_area}` : '',
        ingredients: ingredients ? `${$i18n.t('Ingredients')}: ${ingredients}` : '',
        formulation_origin: formulation_origin ? `${$i18n.t('Formulation origin')}: ${formulation_origin}` : '',
        history: history ? `${$i18n.t('History')}: ${history}` : '',
        hint: prod_hint,
        user_experience: user_experience ? `${$i18n.t('User experience')}: ${user_experience}` : '',
        source: source ? source : '',
        reference_link: reference_link ? reference_link : '',
    })

    const getQNAMetadata = () => ({
        scope: scope,
        question: question,
        answer: answer,
        hint: qna_hint,
    })

    const getRecommendationMetadata = (): Omit<Recommendation, 'id'> => ({
        tags: rec_tags,
        recommended,
        suitable,
        info,
        hint: rec_hint,
    })

    const setProductData = (product: Product) => {
        product_id = product.id;
        product_name = product.name;
        categories = product.categories;
        tags = product.tags;
        similar_products = product.similar_products || '';
        recommended_products = product.recommended_products || '';
        supporting_products = product.supporting_products || '';
        combinable_with = product.combinable_with || '';
        short_description = product.short_description;
        product_details = product.product_details || '';
        target_audience = product.target_audience || '';
        intake_recommendation = product.intake_recommendation;
        application_area = product.application_area || '';
        ingredients = product.ingredients;
        formulation_origin = product.formulation_origin || '';
        history = product.history || '';
        prod_hint = product.hint || '';
        user_experience = product.user_experience || '';
        reference_link = product.reference_link;
    }

    const setQNAData = (qna: QNA) => {
        qna_id = qna.id;
        scope = qna.scope;
        question = qna.question;
        answer = qna.answer;
        qna_hint = qna.hint;
    }

    const setRecommendationData = (recommendation: Recommendation) => {
        rec_id = recommendation.id;
        rec_tags = recommendation.tags;
        recommended = recommendation.recommended;
        suitable = recommendation.suitable;
        info = recommendation.info;
        rec_hint = recommendation.hint;
    }

    const resetProductData = (evt: SubmitEvent) => {
        product_id = '';
        product_name = '';
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
        prod_hint = '';
        user_experience = '';
        reference_link = '';

        (evt.target as HTMLElement).querySelectorAll('textarea').forEach((el: HTMLElement) => {
            el.style.height = '';
        });

        setProductSubmitDisabled();
    }

    const resetQNAData = (evt: SubmitEvent) => {
        qna_id = '';
        scope = '';
        question = '';
        answer = '';
        qna_hint = '';

        const el: HTMLElement = (evt.target as HTMLElement).querySelector('textarea') as HTMLElement;
        el.style.height = '';

        setQNASubmitDisabled();
    }

    const resetRecommendationData = (evt: SubmitEvent) => {
        rec_id = '';
        rec_tags = '';
        recommended = '';
        suitable = '';
        info = '';
        rec_hint = '';

        const el: HTMLElement = (evt.target as HTMLElement).querySelector('textarea') as HTMLElement;
        el.style.height = '';

        setRecommendationSubmitDisabled();
    }

    const onProductSubmit = async (evt: SubmitEvent) => {
        if (disabled) {
            toast.error($i18n.t('Please fill in all mandatory fields'));
            return;
        }
        disabled = true;
        await processProductHandler(localStorage.token, product_id, getProductMetadata());
        resetProductData(evt);
    }

    const onQNASubmit = async (evt: SubmitEvent) => {
        if (qna_disabled) {
            toast.error($i18n.t('Please fill in all mandatory fields'));
            return;
        }
        qna_disabled = true;
        await processQNAHandler(localStorage.token, qna_id, getQNAMetadata());
        resetQNAData(evt);
    }

    const onRecommendationSubmit = async (evt: SubmitEvent) => {
        if (recommendations_disabled) {
            toast.error($i18n.t('Please fill in all mandatory fields'));
            return;
        }
        recommendations_disabled = true;
        await processRecommendationHandler(localStorage.token, rec_id, getRecommendationMetadata());
        resetRecommendationData(evt);
    }

    const onProductSearch = async () => {
        const product = await getProductByNameHandler(localStorage.token, search_name);
        if (product) {
            setProductData(product);
            setProductSubmitDisabled();
        }
    }

    const onQNASearch = async () => {
        const qna = await getQNAByQuestionHandler(localStorage.token, search_question);
        if (qna) {
            setQNAData(qna);
            setQNASubmitDisabled();
        }
    }

    const onRecommendationSearch = async () => {
        const recommendation = await getRecommendationByTagHandler(localStorage.token, search_tag);
        if (recommendation) {
            setRecommendationData(recommendation);
            setRecommendationSubmitDisabled();
        }
    }

    const onResetProductForm = (evt: SubmitEvent) => {
        resetProductData(evt);
    }

    const onResetQNAForm = (evt: SubmitEvent) => {
        resetQNAData(evt);
    }

    const onResetRecommendationForm = (evt: SubmitEvent) => {
        resetRecommendationData(evt);
    }

    let search_name = '';
    let search_question = ''
    let search_tag = ''
    // Tab state
    let activeTab = 'products';

    function switchTab(tab: string) {
        activeTab = tab;
    }

</script>

<div class="tabs-container">
    <!-- Tab Navigation -->
    <div class="tab-nav">
        <button
                class="tab-button {activeTab === 'products' ? 'active' : ''}"
                on:click={() => switchTab('products')}
        >
            <div class="self-center mr-2">
                <svg
                        viewBox="0 0 24 24"
                        xmlns="http://www.w3.org/2000/svg"
                        fill="currentColor"
                        class="w-4 h-4"
                >
                    <path d="m22.987 14.896c-.107-.318-.366-.561-.689-.647-.087-.024-1.853-.467-4.284-.084.311-.361.619-.74.918-1.142 2.705-3.636 3.086-6.779 3.102-6.911.039-.354-.111-.702-.397-.915s-.664-.258-.99-.117c-.122.052-3.021 1.322-5.727 4.958-.142.191-.277.383-.409.574.017-.365.029-.735.029-1.113 0-4.889-1.552-7.848-1.618-7.972-.348-.65-1.416-.65-1.764 0-.066.124-1.618 3.083-1.618 7.972 0 .383.012.758.03 1.128-.144-.21-.292-.42-.448-.629-2.707-3.636-5.606-4.906-5.728-4.958-.326-.141-.704-.096-.99.117-.286.212-.437.561-.397.915.016.132.396 3.274 3.102 6.911.299.402.607.781.918 1.142-2.431-.383-4.197.06-4.284.084-.323.086-.582.33-.689.647-.106.318-.047.667.159.932.059.076 1.479 1.865 4.693 2.77 1.277.36 2.526.493 3.578.53-.552.428-1.157.8-1.725.942-.536.134-.862.677-.728 1.213.131.54.69.862 1.212.728 1.013-.253 1.974-.888 2.758-1.535v1.564c0 .552.447 1 1 1s1-.448 1-1v-1.564c.783.647 1.744 1.281 2.758 1.535.522.134 1.08-.188 1.212-.728.135-.536-.191-1.079-.728-1.213-.55-.138-1.135-.491-1.674-.902 1.049-.038 2.294-.171 3.566-.529 3.215-.905 4.635-2.694 4.693-2.77.206-.265.266-.614.159-.932z"/>
                </svg>
            </div>
            {$i18n.t('Products')}
        </button>
        <button
                class="tab-button {activeTab === 'qna' ? 'active' : ''}"
                on:click={() => switchTab('qna')}
        >
            <div class="self-center mr-2">
                <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        class="w-4 h-4"
                >
                    <path d="M9,0C4.038,0,0,4.037,0,9v9H9c4.963,0,9-4.037,9-9S13.963,0,9,0Zm1,14.077h-2v-2.077h2v2.077Zm.447-4.448c-.188,.103-.447,.563-.447,.876v.495h-2v-.495c0-1.033,.637-2.163,1.481-2.628,.29-.159,.595-.535,.502-1.066-.069-.392-.402-.725-.793-.793-.306-.056-.602,.022-.832,.216-.228,.19-.358,.47-.358,.767h-2c0-.889,.391-1.727,1.072-2.299,.681-.572,1.577-.814,2.463-.653,1.209,.211,2.204,1.205,2.417,2.417,.223,1.272-.382,2.543-1.506,3.164Zm13.553,6.371v8h-8c-2.955,0-5.535-1.615-6.92-4.004h0c6.011-.043,10.873-4.905,10.916-10.916h0c2.389,1.385,4.004,3.965,4.004,6.92Z"/>
                </svg>
            </div>
            {$i18n.t('FAQ')}
        </button>
        <button
                class="tab-button {activeTab === 'recommendations' ? 'active' : ''}"
                on:click={() => switchTab('recommendations')}
        >
            <div class="self-center mr-2">
                <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        class="w-4 h-4"
                >
                    <path d="M16,2h-.171c-.413-1.164-1.525-2-2.829-2h-2c-1.304,0-2.416,.836-2.829,2h-.171c-2.757,0-5,2.243-5,5v12c0,2.757,2.243,5,5,5h8c2.757,0,5-2.243,5-5V7c0-2.757-2.243-5-5-5ZM7,18c-.552,0-1-.448-1-1s.448-1,1-1,1,.448,1,1-.448,1-1,1Zm10,0h-6c-.552,0-1-.448-1-1s.448-1,1-1h6c.552,0,1,.448,1,1s-.448,1-1,1ZM7,14c-.552,0-1-.448-1-1s.448-1,1-1,1,.448,1,1-.448,1-1,1Zm10,0h-6c-.552,0-1-.448-1-1s.448-1,1-1h6c.552,0,1,.448,1,1s-.448,1-1,1ZM7,10c-.552,0-1-.448-1-1s.448-1,1-1,1,.448,1,1-.448,1-1,1Zm10,0h-6c-.552,0-1-.448-1-1s.448-1,1-1h6c.552,0,1,.448,1,1s-.448,1-1,1Z"/>
                </svg>
            </div>
            {$i18n.t('Recommendations')}
        </button>
        <button
                class="tab-button {activeTab === 'export' ? 'active' : ''}"
                on:click={() => switchTab('export')}
        >
            <div class="self-center mr-2">
                <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 8 8"
                        fill="currentColor"
                        class="w-4 h-4"
                >
                    <path fill-rule="evenodd" d="M2.12.794a.8.8 0 0 0-.745.53h5.73a.8.8 0 0 0-.746-.53zm-1.06 1.06a.801.801 0 0 0-.796.797v4.238c0 .436.36.797.797.797H7.42a.8.8 0 0 0 .794-.797V2.651a.8.8 0 0 0-.794-.797zm3.185 1.057a.265.265 0 0 1 .182.077l1.06 1.06a.265.265 0 1 1-.373.374l-.609-.607v2.54a.265.265 0 1 1-.53 0V3.814l-.608.608a.265.265 0 0 1-.215.08.265.265 0 0 1-.159-.454l1.06-1.06a.265.265 0 0 1 .192-.077z" paint-order="stroke fill markers" />
                </svg>
            </div>
            {$i18n.t('Export')}
        </button>
    </div>

    <!-- Tab Content -->
    <div class="tab-content">
        {#if activeTab === 'products'}
            <div class="tab-pane" id="products-tab">
                <div>
                    <div class="text-lg font-semibold mb-2">
                        {$i18n.t('Create or edit a product')}
                    </div>
                    <div class="border border-gray-100 dark:border-gray-800 rounded-md p-3">
                        <form class="flex justify-between space-y-3 text-sm"
                              on:submit|preventDefault={onProductSearch}>
                            <span class="flex-1">
                                <input class="w-full disabled:text-gray-500" type="text" bind:value="{search_name}" placeholder="🔎 {$i18n.t('Search product by name')}" disabled={!disabled}>
                                <div class="text-xs text-gray-500">{$i18n.t('To update a product, first find it by name to populate its fields.')}</div>
                            </span>
                            <span class="flex-none">
                                <input type="submit" class="button w-fit mb-3 ml-5" value="{$i18n.t('Search')}" disabled={!disabled}>
                            </span>
                        </form>
                    </div>
                    <form class="flex flex-col justify-between space-y-3 text-sm mt-10" on:submit|preventDefault={onProductSubmit} on:reset|preventDefault={onResetProductForm}>
<!--                        <div class="w-full text-xs mt-5 text-right"> - {$i18n.t('Mandatory Fields')}</div>-->
                        <input type="hidden" bind:value="{product_id}" placeholder="{$i18n.t('Wird ein neues Produkt angelegt, wenn leer')}">

                        <label class="mb-0 font-bold text-teal-500" for="name">{$i18n.t('Product name')}</label>
                        <input type="text" bind:value="{product_name}" on:input={setProductSubmitDisabled} on:keydown={setProductSubmitDisabled}>

                        <label class="mb-0 font-bold text-teal-500" for="categories">{$i18n.t('Categories')}</label>
                        <input type="text" bind:value="{categories}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Tibetische Rezeptur Lung')}" on:input={setProductSubmitDisabled} on:keydown={setProductSubmitDisabled}>

                        <label class="mb-0 font-bold text-teal-500" for="tags">{$i18n.t('Tags')}</label>
                        <input type="text" bind:value="{tags}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Shake, Shape Classic, Abnehmen, Wohlfühlen , Konzept')}" on:input={setProductSubmitDisabled} on:keydown={setProductSubmitDisabled}>

                        <label class="mb-0" for="recommended_products">{$i18n.t('Recommended products')}</label>
                        <input type="text" bind:value="{recommended_products}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Omega Go!, Omega 3 Orange')}">

                        <label class="mb-0" for="similar_products">{$i18n.t('Similar products')}</label>
                        <input type="text" bind:value="{similar_products}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Algenkraft, Gehirnkraft, Darmkraft')}">

                        <label class="mb-0" for="supporting_products">{$i18n.t('Supporting products')}</label>
                        <input type="text" bind:value="{supporting_products}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Chili Shoko Shake, Burner, daily 365')}">

                        <label class="mb-0" for="combinable_with">{$i18n.t('Combinable with products')}</label>
                        <input type="text" bind:value="{combinable_with}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Lung, Omega Go!, Omega 3 Orange')}">

                        <label class="mb-0 font-bold text-teal-500" for="short_description">{$i18n.t('Short description')}</label>
                        <Textarea bind:value="{short_description}" on:input={setProductSubmitDisabled} onKeydown={setProductSubmitDisabled}/>

                        <label class="mb-0" for="product_details">{$i18n.t('Product details')}</label>
                        <Textarea bind:value="{product_details}"/>

                        <label class="mb-0" for="target_audience">{$i18n.t('Target audience')}</label>
                        <Textarea bind:value="{target_audience}"/>

                        <label class="mb-0" for="application_area">{$i18n.t('Application area')}</label>
                        <Textarea bind:value="{application_area}"/>

                        <label class="mb-0" for="formulation_origin">{$i18n.t('Formulation origin')}</label>
                        <Textarea bind:value="{formulation_origin}"/>

                        <label class="mb-0 font-bold text-teal-500" for="intake_recommendation">{$i18n.t('Intake recommendation')}</label>
                        <Textarea bind:value="{intake_recommendation}" on:input={setProductSubmitDisabled} onKeydown={setProductSubmitDisabled}/>

                        <label class="mb-0 font-bold text-teal-500" for="ingredients">{$i18n.t('Ingredients')}</label>
                        <Textarea bind:value="{ingredients}" on:input={setProductSubmitDisabled} on:keydown={setProductSubmitDisabled}/>

                        <label class="mb-0" for="history">{$i18n.t('History')}</label>
                        <Textarea bind:value="{history}"/>

                        <label class="mb-0" for="user_experience">{$i18n.t('User experience')}</label>
                        <Textarea bind:value="{user_experience}" placeholder="ℹ️ {$i18n.t('Zum Beispiel: Monika S., 57 Jahre. \"Es ist erstaunlich, wie einfach es sein kann, für die eigene Gesundheit etwas zu tun... \"')}"/>

                        <label class="mb-0 font-bold text-teal-500" for="reference_link">{$i18n.t('Product webpage')}</label>
                        <input type="text" bind:value="{reference_link}" placeholder="ℹ️ {$i18n.t('Direkter Link zum Produkt im Shop oder Webseite')}"  on:input={setProductSubmitDisabled} on:keydown={setProductSubmitDisabled}>

                        <label class="mb-0" for="prod_hint">{$i18n.t('Mentora Pro hint')} 💡</label>
                        <Textarea bind:value="{prod_hint}" placeholder="Nimm anstelle Wasser mal Tee mit Zitrone um die Wirkung von Produkt zu verbessern."/>

                        <div class="text-center mb-10">
                            <input type="reset" value="{$i18n.t('Zurücksetzen')}" class="button-danger w-fit mt-5 mr-3">
                            <input type="submit" value="{$i18n.t('Save')}" class="button w-fit mt-5" disabled={disabled}>
                        </div>
                    </form>
                </div>
            </div>
        {/if}

        {#if activeTab === 'qna'}
            <div class="tab-pane" id="qna-tab">
                <div class="qna-container">
                    <div class="text-lg font-semibold mb-4">
                        {$i18n.t('Create or edit FAQs')}
                    </div>
                    <div class="mt-2 mb-3">⚠️ {$i18n.t('Search for existing similar questions before creating a new one to prevent duplicates.')}</div>
                    <div class="border border-gray-100 dark:border-gray-800 rounded-md p-3">
                        <form class="flex justify-between space-y-3 text-sm"
                              on:submit|preventDefault={onQNASearch}>
                            <span class="flex-1">
                                <input class="w-full disabled:text-gray-500" type="text" bind:value="{search_question}" placeholder="🔎 {$i18n.t('Find similar questions')}" disabled={!qna_disabled}>
                                <div class="text-xs text-gray-500 mt-2">{$i18n.t('Search to find and edit an existing question or its answer.')}</div>
                            </span>
                            <span class="flex-none">
                                <input type="submit" class="button w-fit mb-3 ml-5" value="{$i18n.t('Search')}" disabled={!qna_disabled}>
                            </span>
                        </form>
                    </div>
                    <form class="flex flex-col justify-between space-y-3 text-sm mt-10"
                          on:submit|preventDefault={onQNASubmit}
                          on:reset|preventDefault={onResetQNAForm}>
                        <input type="hidden" bind:value="{qna_id}">

                        <div class=" mb-5 text-right">
                            <select class="dark:bg-gray-900 bg-gray-50 w-fit pr-8 rounded-sm px-2 p-1 text-sm outline-hidden text-teal-500" bind:value="{scope}" on:change={setQNASubmitDisabled}>
                                <option value="">{$i18n.t('Select scope')}</option>
<!--                                <option value="recommendations">{$i18n.t('Recommendations')}</option>-->
                                <option value="qna">{$i18n.t('FAQ')}</option>
                                <option value="global">{$i18n.t('Global')}</option>
<!--                                <option value="disclaimer">{$i18n.t('Disclaimer')}</option>-->
                            </select>
                        </div>

                        <label class="mb-0 font-bold text-teal-500" for="question">{$i18n.t('Question')}</label>
                        <input type="text" bind:value="{question}" on:keydown={setQNASubmitDisabled}>

                        <label class="mb-0 font-bold text-teal-500" for="answer">{$i18n.t('Answer')}</label>
                        <Textarea bind:value="{answer}" onKeydown={setQNASubmitDisabled} onInput={setQNASubmitDisabled}/>

                        <label class="mb-0" for="qna_hint">{$i18n.t('Mentora Pro hint')} 💡</label>
                        <Textarea bind:value="{qna_hint}" placeholder="Nimm anstelle Wasser mal Tee mit Zitrone um die Wirkung von Produkt zu verbessern."/>

                        <div class="text-center mb-10">
                            <input type="reset" value="{$i18n.t('Reset')}" class="button-danger w-fit mt-5 mr-3">
                            <input type="submit" value="{$i18n.t('Save')}" class="button w-fit mt-5" disabled={qna_disabled}>
                        </div>
                    </form>
                </div>
            </div>
        {/if}

        {#if activeTab === 'recommendations'}
            <div class="tab-pane" id="recommendations-tab">
                <div class="recommendations-container">
                    <div class="text-lg font-semibold mb-4">
                        {$i18n.t('Create or edit product recommendation')}
                    </div>
                    <div class="mt-2 mb-3">⚠️ {$i18n.t('To prevent duplicates search for existing tags before creating a new recommendation.')}</div>
                    <div class="border border-gray-100 dark:border-gray-800 rounded-md p-3">
                        <form class="flex justify-between space-y-3 text-sm"
                              on:submit|preventDefault={onRecommendationSearch}>
                            <span class="flex-1">
                                <input class="w-full disabled:text-gray-500" type="text" bind:value="{search_tag}" placeholder="🔎 {$i18n.t('Find existing tag')}" disabled={!recommendations_disabled}>
                                <div class="text-xs text-gray-500 mt-2">{$i18n.t('Search for tag to find and edit an existing recommendation.')}</div>
                            </span>
                            <span class="flex-none">
                                <input type="submit" class="button w-fit mb-3 ml-5" value="{$i18n.t('Search')}" disabled={!recommendations_disabled}>
                            </span>
                        </form>
                    </div>
                    <form class="flex flex-col justify-between space-y-3 text-sm mt-10"
                          on:submit|preventDefault={onRecommendationSubmit}
                          on:reset|preventDefault={onResetRecommendationForm}>
                        <input type="hidden" bind:value="{rec_id}">

                        <label class="mb-0 font-bold text-teal-500" for="rec_tags">{$i18n.t('Tags')}</label>
                        <input type="text" bind:value="{rec_tags}" on:keydown={setRecommendationSubmitDisabled} placeholder="Allergien">

                        <label class="mb-0 font-bold text-teal-500" for="recommended">{$i18n.t('Recommended products')}</label>
                        <input type="text" bind:value="{recommended}" on:keydown={setRecommendationSubmitDisabled} placeholder="OPC-Kraft, Darmkraft, Inflam-Komplex, Omega 3 plus">

                        <label class="mb-0 font-bold text-teal-500" for="suitable">{$i18n.t('Suitable products')}</label>
                        <input type="text" bind:value="{suitable}" on:keydown={setRecommendationSubmitDisabled} placeholder="Wurzel-Komplex, Pilzkraft, Eiweiß-Vitalkomplex, Algenkraft, Enzymkraft, Leberkraft, Ayurveda Balance, Gehirnkraft, Lungenkraft">

                        <label class="mb-0 font-bold text-teal-500" for="suitable">{$i18n.t('Indications for use')}</label>
                        <Textarea bind:value="{info}" onKeydown={setRecommendationSubmitDisabled} onInput={setRecommendationSubmitDisabled} placeholder="OPC-Kraft, Darmkraft, Inflam-Komplex und Omega-3 Plus unterstützen dich dabei, Entzündungen..."/>

                        <label class="mb-0" for="rec_hint">{$i18n.t('Mentora Pro hint')} 💡</label>
                        <Textarea bind:value="{rec_hint}" placeholder="Nimm anstelle Wasser mal Tee mit Zitrone um die Wirkung von Produkt zu verbessern."/>

                        <div class="text-center mb-10">
                            <input type="reset" value="{$i18n.t('Reset')}" class="button-danger w-fit mt-5 mr-3">
                            <input type="submit" value="{$i18n.t('Save')}" class="button w-fit mt-5" disabled={recommendations_disabled}>
                        </div>
                    </form>
                </div>
            </div>
        {/if}

        {#if activeTab === 'export'}
            <div class="tab-pane" id="export-tab">
                <form
                        class="flex flex-col justify-between space-y-3 text-sm"
                        on:submit|preventDefault={async () => {
                        saveHandler();
                    }}
                >
                    <div class=" space-y-3 overflow-y-scroll scrollbar-hidden">
                        <div>
                            <div class=" mb-2 text-lg font-medium">{$i18n.t('Export')}</div>

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
                                        <path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3Z"/>
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
                                        <path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3Z"/>
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

                            <hr class="border-gray-100 dark:border-gray-850 my-1"/>

                            {#if $config?.features.enable_admin_export}
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
                                            <path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3Z"/>
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
                </form>
            </div>
        {/if}

    </div>
</div>

<style>
    .tabs-container {
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
    }

    .tab-nav {
        display: flex;
        border-bottom: 1px solid #e2e8f0;
        background-color: transparent;
        margin-bottom: 0;
    }

    .tab-button {
        padding: 8px 20px;
        border: none;
        background-color: transparent;
        cursor: pointer;
        font-weight: 500;
        color: lightgray;
        border-bottom: 2px solid transparent;
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        font-size: 0.875rem;
    }

    .tab-button:hover {
        color: black;
    }

    .tab-button.active {
        color: black;
    }

    .tab-content {
        flex: 1;
        background-color: white;
        overflow-y: auto;
    }

    .tab-pane {
        padding: 24px;
        height: 100%;
        animation: fadeIn 0.3s ease-in-out;
    }

    .qna-container {
        height: 100%;
        display: flex;
        flex-direction: column;
    }

    @keyframes fadeIn {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    /* Dark mode support */
    :global(.dark) .tab-nav {
        background-color: transparent;
        border-bottom-color: var(--color-gray-800);
    }

    :global(.dark) .tab-button {
        color: dimgray;
    }

    :global(.dark) .tab-button:hover {
        color: white;
        background-color: transparent;
    }

    :global(.dark) .tab-button.active {
        color: white;
        background-color: transparent;
    }

    :global(.dark) .tab-content {
        background-color: transparent;
    }
</style>
