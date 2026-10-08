# Check a driver

The template brings `checks.py`, so the driver can check itself against
this page. It is part of your driver, not of the controller.

```python
from my_scope.checks import validate_driver, check_acquire_answer
from my_scope.zmart_driver import ZmartDriver

validate_driver(ZmartDriver, connection)
```

`validate_driver` connects, calls every `get_*` method, and returns the
problems it found, one plain sentence each. An empty list means every
answer fits. It moves nothing and acquires nothing, so one acquisition is
checked separately, in the driver's own tests, on a simulator or a test
bench:

```python
answer = mic.acquire(position_label="A2")
check_acquire_answer(answer)
```

The loop to work in while you write a driver is this: write a method,
validate, read the problems, repeat.

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich. thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com.
