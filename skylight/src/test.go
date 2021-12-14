package main

import (
	"bufio"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	retryCount = 1

	resetDisk      = 0xDEADBEEF
	diskSize       = 76 << 10
	trackSize      = 4096
	pageSize       = 4096
	blockSize      = pageSize
	bandSizeTracks = 3
	cachePercent   = 40
	pbaSize        = 4096
	lbaSize        = 512

	moduleName   = "sadc"
	blockDevice  = "/dev/sdb"
	modulePath   = "dm-" + moduleName + ".ko"
	moduleRmName = "dm_" + moduleName
	targetName   = moduleName
	targetDevice = "/dev/mapper/" + targetName
)

func panicf(format string, v ...interface{}) {
	s := fmt.Sprintf(format, v...)
	panic(s)
}

func numUsableSectors() int {
	bandSize := bandSizeTracks * trackSize
	numBands := diskSize / bandSize
	numCacheBands := numBands * cachePercent / 100
	numDataBands := (numBands/numCacheBands - 1) * numCacheBands
	return numDataBands * bandSize / lbaSize
}

// |cmdLine| is a shell command that may include pipes.  Returns the slice of
// |exec.Command| objects all of which have been started with the exception of
// the last one.
func chainCmds(cmdLine string) (cmds []*exec.Cmd) {
	for _, s := range strings.Split(cmdLine, "|") {
		args := strings.Fields(s)
		cmds = append(cmds, exec.Command(args[0], args[1:]...))
	}

	for i, c := range cmds[:len(cmds)-1] {
		stdout, err := c.StdoutPipe()
		if err != nil {
			panicf("Failed to get stdout of %s: %v", c.Path, err)
		}
		err = c.Start()
		if err != nil {
			panicf("Failed to run %s: %v", c.Path, err)
		}
		cmds[i+1].Stdin = stdout
	}
	return
}

// Runs |cmdLine|, which is a shell command that may include pipes.
func runCmd(cmdLine string) {
	cmds := chainCmds(cmdLine)

	c := cmds[len(cmds)-1]

	if _, err := c.Output(); err != nil {
		panicf("Failed to run %s: %v\n", c.Path, err)
	}
}

// Runs |cmdLine|, which is a shell command that may include pipes and returns
// the stdout of the last command.
func startCmd(cmdLine string) io.ReadCloser {
	cmds := chainCmds(cmdLine)

	c := cmds[len(cmds)-1]

	stdout, err := c.StdoutPipe()
	if err != nil {
		panicf("Failed to get stdout of %s: %v\n", c.Path, err)
	}

	if err := c.Start(); err != nil {
		panicf("Failed to start %s: %v\n", c.Path, err)
	}
	return stdout
}

func setup() {
	fmt.Println("Setting up test environment...")

	runCmd("make clean")
	runCmd("make")
	runCmd("sudo insmod " + modulePath)

	c := fmt.Sprintf("echo 0 %d %s %s %d %d %d %d | sudo dmsetup create %s",
		numUsableSectors(), targetName, blockDevice, trackSize,
		bandSizeTracks, cachePercent, diskSize, targetName)
	runCmd(c)
}

func tearDown() {
	fmt.Println("Tearing down test environment...")

	runCmd("sudo dmsetup remove " + targetName)
	runCmd("sudo rmmod " + moduleRmName)
}

// Allocates aligned blocks for direct I/O.
func alignedBlocks(pattern string) []byte {
	count := len(pattern)
	b := make([]byte, pageSize+blockSize*count)
	a := int(uintptr(unsafe.Pointer(&b[0])) & (pageSize - 1))

	o := 0
	if a != 0 {
		o = pageSize - a
	}
	b = b[o : o+blockSize*count]

	for i := 0; i < count; i++ {
		for j := 0; j < blockSize; j++ {
			b[i*blockSize+j] = pattern[i]
		}
	}
	return b
}

// Writes |len(pattern)| number of blocks filled with |pattern[i]|, starting at
// |blockNo|.
func writeBlocks(f *os.File, blockNo int, pattern string) string {
	b := alignedBlocks(pattern)

	offset := int64(blockNo * blockSize)
	if _, err := f.WriteAt(b, offset); err != nil {
		return fmt.Sprintf("Write failed: %v", err)
	}
	return ""
}

// Reads |len(pattern)| number of blocks starting at |blockNo| and verifies that
// the read blocks' contents match the |pattern|.
func readBlocks(f *os.File, blockNo int, pattern string) string {
	count := len(pattern)
	b := alignedBlocks(strings.Repeat("!", count))

	offset := int64(blockNo * blockSize)
	if _, err := f.ReadAt(b, offset); err != nil {
		panicf("Read failed: %v", err)
	}
	for i := 0; i < count; i++ {
		if pattern[i] == '_' {
			continue
		}
		for j := 0; j < blockSize; j++ {
			if b[i*blockSize+j] != pattern[i] {
				return fmt.Sprintf("Expected %c, got %c",
					pattern[i],
					b[i*blockSize+j])
			}
		}
	}
	return ""
}

// Sends IOCTL to SMR emulator target to reset its state.  Also, overwrite the
// underlying file with zeroes.
func doResetDisk() {
	d, err := os.Open(targetDevice)
	if err != nil {
		panicf("os.Open(%s) failed: %v", targetDevice, err)
	}
	defer d.Close()

	_, _, errr := syscall.Syscall(syscall.SYS_IOCTL, d.Fd(), resetDisk, 0)
	if errr != 0 {
		panicf("Resetting %s failed: %v", targetDevice, errr)
	}

	f, err := os.OpenFile(blockDevice, os.O_RDWR|syscall.O_DIRECT, 0666)
	if err != nil {
		panicf("os.OpenFile(%s) failed: %v", blockDevice, err)
	}
	defer f.Close()

	b := alignedBlocks("\x00")
	for i := 0; i < diskSize/blockSize; i++ {
		if _, err := f.Write(b); err != nil {
			panicf("Failed to write to %s: %v", blockDevice, err)
		}
	}
}

// Verifies syntax of the tests.
func verify(tests []string) {
	var userCmdRegexp = regexp.MustCompile(`^[wr]\s[a-z_]+\s\d+$`)
	var btEventRegexp = regexp.MustCompile(`^[wr]\s\d+\s\d+$`)

	fmt.Println("Verifying syntax of tests...")
	for i, t := range tests {
		fields := strings.Split(t, ":")
		userCmds, btEvents := fields[0], fields[1]

		for _, c := range strings.Split(userCmds, ",") {
			if !userCmdRegexp.MatchString(c) {
				panicf("Bad user command %d: %s", i, c)
			}
		}
		for _, e := range strings.Split(btEvents, ",") {
			if !btEventRegexp.MatchString(e) {
				panicf("Bad blktrace event d: %s", i, e)
			}
		}
	}
}

// Executes a user test command.
func doUserCmd(f *os.File, cmd string) string {
	fs := strings.Fields(cmd)
	operation, pattern := fs[0], fs[1]
	offset, _ := strconv.Atoi(fs[2])

	var s string
	if operation == "w" {
		s = writeBlocks(f, offset, pattern)
	} else {
		s = readBlocks(f, offset, pattern)
	}
	if s != "" {
		s += " [" + cmd + "]"
	}
	return s
}

// Reads blktrace events from |pipe|.
func readBtEvents(pipe io.ReadCloser, ch chan []string, count int) {
	var events []string
	go func() {
		scanner := bufio.NewScanner(pipe)
		for scanner.Scan() {
			s := scanner.Text()
			if !strings.HasPrefix(s, "!") {
				continue
			}
			events = append(events, btToTest(s))
		}
	}()

	// Try to read one more than needed to detect invalid tests that produce
	// more events than we expect.
	count++

	i := 0
	for {
		time.Sleep(1 * time.Second)
		if len(events) == count {
			break
		}
		if i == retryCount {
			break
		}
		i++
	}
	ch <- events
}

func frame(s string) string {
	border := strings.Repeat("-", len(s))
	return fmt.Sprintf("%s\n%s\n%s", border, s, border)
}

// Converts blktrace event to our test format.
func btToTest(btCmd string) string {
	fs := strings.Split(btCmd, ",")
	if len(fs) != 3 {
		return ""
	}

	op := strings.ToLower(fs[0])[1]
	offset, _ := strconv.Atoi(fs[1])
	blocks, _ := strconv.Atoi(fs[2])

	return fmt.Sprintf("%c %d %d", op, offset/8, blocks/8)
}

func eventsMatch(expectedEvents, readEvents []string) bool {
	if len(expectedEvents) != len(readEvents) {
		return false
	}

	sort.Strings(expectedEvents)
	sort.Strings(readEvents)

	for i := range expectedEvents {
		if expectedEvents[i] != readEvents[i] {
			return false
		}
	}
	return true
}

func doTest(i int, test string) {
	f, err := os.OpenFile(targetDevice, os.O_RDWR|syscall.O_DIRECT, 0666)
	if err != nil {
		panicf("os.OpenFile(%s) failed: %v", targetDevice, err)
	}
	defer f.Close()

	c := fmt.Sprintf("sudo blktrace -d %s -o - | blkparse -FQ,%s -i -",
		blockDevice, `!%d,%S,%n\n`)
	pipe := startCmd(c)
	defer func() {
		pipe.Close()
	}()

	fmt.Printf("Running test %3d: ", i)

	fields := strings.Split(test, ":")
	userCmds, btEvents := fields[0], fields[1]

	expectedEvents := strings.Split(btEvents, ",")

	ch := make(chan []string)
	go readBtEvents(pipe, ch, len(expectedEvents))

	// Although at this point blktrace has already started running, there is
	// a race between blktrace issuing BLKTRACESETUP to the block device and
	// us executing the user commands.  Since there is no way of finding out
	// whether blktrace has issued BLKTRACESETUP, we sleep here and hope
	// that it does so before we start executing commands.
	time.Sleep(1 * time.Second)
	for _, cmd := range strings.Split(userCmds, ",") {
		if s := doUserCmd(f, cmd); s != "" {
			panicf("User command failed for the test\n%s\n\n%s",
				frame(test), s)
		}
	}
	runCmd("sudo pkill -15 blktrace")

	readEvents := <-ch
	close(ch)

	if eventsMatch(expectedEvents, readEvents) {
		fmt.Println("ok")
	} else {
		panicf("Blktrace validation failed for the test\n%s\n\n%s",
			frame(test),
			fmt.Sprintf("Expected\n%s\ngot\n%s",
				frame(strings.Join(expectedEvents, "\n")),
				frame(strings.Join(readEvents, "\n"))))
	}
}

func readTests(fileName string) (tests []string) {
	f, err := os.Open(fileName)
	if err != nil {
		panicf("os.Open(%s) failed: %s\n", fileName, err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		s := scanner.Text()
		if s == "" || strings.HasPrefix(s, "#") {
			continue
		}
		tests = append(tests, s)
	}
	return
}

func main() {
	testFile := flag.String("f", "", "File containig tests.")

	flag.Parse()

	if *testFile == "" {
		fmt.Println("Please specify a test file using -f")
		return
	}

	tests := readTests(*testFile)
	verify(tests)

	setup()
	defer tearDown()

	for i, t := range tests {
		doResetDisk()
		doTest(i, t)

		// Killing and immediately restarting blktrace does not work, so
		// we sleep a little.
		time.Sleep(time.Second)
	}
}
