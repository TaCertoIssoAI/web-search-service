from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "WS_"}

    browser_pool_size: int = 5
    browser_headless: bool = True
    context_acquire_timeout: float = 30.0

    default_n_results: int = 10
    max_n_results: int = 50

    search_navigation_timeout: int = 30000
    search_result_wait_timeout: int = 10000

    min_action_delay: float = 0.5
    max_action_delay: float = 2.0

    host: str = "0.0.0.0"
    port: int = 6050


settings = Settings()
