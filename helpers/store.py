from pydux import create_store, combine_reducers,apply_middleware
from helpers.middleware import thunk
from helpers.reducers import reducers
# Create a store
store=apply_middleware(thunk)(create_store)(combine_reducers(reducers))
