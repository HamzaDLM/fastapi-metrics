def exclude_from_metrics(func):

    def wrapper():
        print("excluded.")
        func()
        print("excluded.")

    return wrapper
