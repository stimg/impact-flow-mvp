from fastapi import APIRouter, HTTPException, Request


##########################################
#
# API routes
#
##########################################

router = APIRouter()

@router.post("/api/product/embeddings")
async def generateEmbedings(
        request: Request,
        form_data: GenerateEmbedForm,
        url_idx: Optional[int] = None,
        user=Depends(get_verified_user),
):
    log.info(f"generate_ollama_batch_embeddings {form_data}")

    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        form_data.model = form_data.model.replace(f"{prefix_id}.", "")

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/embed",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
                **(
                    {
                        "X-OpenWebUI-User-Name": user.name,
                        "X-OpenWebUI-User-Id": user.id,
                        "X-OpenWebUI-User-Email": user.email,
                        "X-OpenWebUI-User-Role": user.role,
                    }
                    if ENABLE_FORWARD_USER_INFO_HEADERS and user
                    else {}
                ),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        data = r.json()
        return data
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )

