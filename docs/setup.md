# Install and register your microscopes

Three steps, all done once per microscope computer. After that, a notebook
needs nothing but `import zmart_controller`.

1. **Install.** The controller needs Python 3.11 or newer and nothing else:

   ```bash
   pip install "git+https://github.com/thomdehoog/ZMART-controller"
   ```

   This installs the controller only. The mock driver lives in the
   repository's `tests/` folder, so to try it, clone the repository instead
   and run `pip install .` inside it.

2. **Configure the microscope, once.** Run the driver's own setup step on that
   computer. It measures and saves what only this microscope can know: where
   (0, 0, 0) is, the travel limits, the calibration. The driver writes them to
   the computer's configuration folder (`C:\ProgramData\zmart-microscopy\`
   on Windows), not into any repository, so a re-clone or an upgrade never
   loses them. Each driver's README says how to run its setup.

3. **Plug the driver in, once.** In any Python session on that computer:

   ```python
   import zmart_controller

   zmart_controller.register_driver("path/to/driver")   # the driver's folder
   ```

   The controller imports the driver, checks that it registers a microscope,
   and writes the driver's location to the same configuration folder. From
   then on, every session plugs it in by itself:

   ```python
   import zmart_controller

   zmart_controller.get_instruments()   # your microscope is listed
   ```

   `forget_driver("path/to/driver")` takes it off the list again. To plug a
   driver in for one session only, pass `remember=False`.

   No microscope at hand? The same line works on the mock driver, so you can
   try the whole flow first. From the repository's folder:
   `zmart_controller.register_driver("tests/mock_zmart_driver")`.
   The controller writes down the driver's full folder, so later sessions
   find it from anywhere on the computer.

The configuration folder is `C:\ProgramData\zmart-microscopy\` on Windows,
`/Library/Application Support/zmart-microscopy/` on macOS and
`/etc/zmart-microscopy/` on Linux. Set `ZMART_MICROSCOPY_ROOT` to use another
folder.

On a computer that several people log in to, the first person to register a
driver creates the configuration folder, and Windows lets only that account
change it. Others can still use the registered drivers, but registering a new
one fails with a message naming the folder. Either do step 3 from the account
that set the computer up, or ask your IT administrator to give the users of
the microscope permission to change `C:\ProgramData\zmart-microscopy\`.

A driver shipped as its own package can skip step 3; see
[Plug in your own driver functions](driver.md).
